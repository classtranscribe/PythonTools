# Copyright (c) 2019 Lawrence Angrave

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# https://docs.microsoft.com/azure/cognitive-services/speech-service/quickstart-python
# https://stackoverflow.com/questions/56842391/how-to-get-word-level-timestamps-using-azure-speech-to-text-and-the-python-sdk
# What is "ITN" https://machinelearning.apple.com/2017/08/02/inverse-text-normal.html
# https://github.com/Azure-Samples/cognitive-services-speech-sdk/tree/master/samples/python/console
# https://github.com/Azure-Samples/cognitive-services-speech-sdk/blob/master/samples/python/console/speech_sample.py
# https://docs.microsoft.com/en-us/python/api/azure-cognitiveservices-speech/azure.cognitiveservices.speech.recognitionresult?view=azure-python
# https://docs.microsoft.com/en-us/azure/cognitive-services/speech-service/rest-speech-to-text

# SDK docs - 
# https://docs.microsoft.com/en-us/python/api/azure-cognitiveservices-speech/azure.cognitiveservices.speech.speechrecognitioneventargs?view=azure-python#result

# Batch (for the future)-
# https://docs.microsoft.com/en-us/azure/cognitive-services/speech-service/batch-transcription
# https://docs.microsoft.com/en-us/azure/cognitive-services/speech-service/batch-transcription#supported-formats


import azure.cognitiveservices.speech as speechsdk
import os
import sys
import atexit
import time
import json


recognizers = []

def shutdown_recognizers():
    global recognizers
    while len(recognizers)>0:
        recognizer = recognizers.pop()
        try:
            # dont waste resources with any long running transcriptions
            recognizer.stop_continuous_recognition()
        except Error as ignored:
              print(ignored)

atexit.register(shutdown_recognizers)

def recognize_pcm_audio_file_to_ms_json(input_pcm_file):
    """Performs speech recognition and returns MS-cognitive-services specific json array """
    global recognizers
    
    # <SpeechContinuousRecognitionWithFile>
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
    
    speech_config.request_word_level_timestamps()
    #https://docs.microsoft.com/en-us/python/api/azure-cognitiveservices-speech/azure.cognitiveservices.speech.profanityoption?view=azure-python
    speech_config.set_profanity(speechsdk.ProfanityOption.Masked)
    
    audio_config = speechsdk.audio.AudioConfig(filename=input_pcm_file)

    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    # For an empty file throws RuntimeError: Exception with an error code: 0x9 (SPXERR_UNEXPECTED_EOF)
    # For a missing file RuntimeError: Exception with an error code: 0x8 (SPXERR_FILE_OPEN_FAILED)
    # RuntimeError: Exception with an error code: 0x8 (SPXERR_FILE_OPEN_FAILED)
    # Garbage text file: RuntimeError: Exception with an error code: 0xa (SPXERR_INVALID_HEADER)
    
    recognizers.append(recognizer)
    
    done = False
    json_results = []
    error_messages = []
    
    def stop_cb(event):
        if recognizer in recognizers:
            recognizers.remove(recognizer)
            recognizer.stop_continuous_recognition()
             # SDK docs claims error_details can be None. In practice it is an empty string for EOF cancel event, so using as a boolean treats both of these as false
            if event.cancellation_details.error_details:
                nonlocal error_messages
                error_messages.append( event.cancellation_details.error_details )
            # Do this last
            nonlocal done
            done = True
 
    def recognized_cb(event):
        nonlocal json_results
        print(event)
        # event.result.json is actually a string, so we parse it here to check for validity
        
        json_results.append( json.loads(event.result.json) )

    recognizer.recognized.connect(recognized_cb) # Here are the words!

    # The MS SDK registers the stop_cb for both continuous recognition or canceled events. Canceled events may/are be genereated at EOF! :-(
    recognizer.session_stopped.connect(stop_cb)
    recognizer.canceled.connect(stop_cb)

    recognizer.start_continuous_recognition()
    while not done:
        time.sleep(.5)

    if error_messages: 
        raise RuntimeError( ','.join(error_messages))
# truncated 1000byte PCM file - "RuntimeError: Exception with an error code: 0x9 (SPXERR_UNEXPECTED_EOF)
# Bad API key - "WebSocket Upgrade failed with an authentication error (401). Please check for correct subscription key (or authorization token) and region name.
            
    return json_results

def save_json(json_results, filename):
    with open(filename, 'w') as out_file:
        json.dump(json_results, out_file)


def main():   
    if len(sys.argv) != 3:
        print ("Usage: {} input_mono_16KHz_pcm_file output_json_file".format(sys.argv[0]) )
        sys.exit(1)
    if not speech_key:
        print('Please set speech_key environment variable to your cognitive-services-key (and also azure_region if not westus)')
        sys.exit(1)
    
    pcm_file = sys.argv[1]
    json_file = sys.argv[2]
    
    json_results = recognize_pcm_audio_file_to_ms_json(pcm_file)
    save_json(json_results, json_file)
    
speech_key = os.environ.get('speech_key','')
service_region = os.environ.get('azure_region','westus') # e.g. westus

# On Mac/Linux terminal put your keys into setenv.sh and use 'source setenv.sh'
# echo 'export speech_key=your-api-key' > setenv.sh
# echo 'export azure_region=westus' >> setenv.sh

# Or put them directly here
#speech_key, service_region = "YOURKEY", "westus"

if __name__== "__main__":
    main()
