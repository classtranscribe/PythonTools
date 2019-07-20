import os
import json
import sys
import re

# https://www.w3.org/TR/webvtt1/

# Example webvtt file
# WEBVTT
#
# 00:11.000 --> 00:13.000
# We are in New York City
#
# 00:13.000 --> 00:16.000
# We’re actually at the Lucern Hotel, just down the street
# Some timing constants
# These values are currently best estimates by Angrave - perhaps there's some official best-practices that could be informative?

MAX_LINES_PER_CAPTION = 2 # Code only supports max 2

FUDGE_START_GAP_MS = 250 # Allow start time of next caption to be a little early, so that endtime-of-last can be exactly starttime of next caption

NOTABLE_SILENCE_MS = 6000 # A gap of more than this and we'll emit a '[ Silence / Inaudible ]' caption

MAX_CAPTION_DURATION_MS = 8000 # One caption should not span more than this number of milliseconds

MAX_INTERWORD_GAP_MS = 1000 # A silence in speech of  more than this and it's time to start a new caption line

MAX_CAPTION_WORDS = 8 * MAX_LINES_PER_CAPTION # Limit the number of words in one caption line (except at the very end of the file)

MAX_CAPTION_CHAR_LENGTH_PER_LINE = 32 # Per line!
# Source https://its.uiowa.edu/support/article/103634
# No more than 2 lines of text per caption.
# Limit yourself to 32 characters per line or approximately 4-8 words.

END_VIDEO_ORPHAN_COUNT = 3 # If we are processing the last few words in the file, then ignore MAX_CAPTION_WORDS and allow a longer last caption line

ACKNOWLEDGEMENT_PRE_DELAY_MS = 1500 # A short gap between end of captions and displaying acknowledgement

ACKNOWLEDGEMENT_DURATION_MS = 3500

ACKNOWLEDGEMENT_TEXT1 = 'Automated Transcriptions by ClassTranscribe,'
ACKNOWLEDGEMENT_TEXT2= 'A University of Illinois Digital Accessibility Project'

PROFANITY_LIST = [ 'homo','gay','slut','damn','ass','poop','cock','lol','crap','sex','noob','nazi','neo-nazi','fuck','fucked',
'bitch','pussy','penis','vagina','whore','shit','nigger','nigga','cocksucker','assrape','motherfucker',
'wanker','cunt','faggot','fags','asshole','fuck']
#Based on https://en.wikipedia.org/wiki/User:ClueBot/Source#Score_list


def mask_profanity(word):
    if not word or (word.lower() not in PROFANITY_LIST): 
        return word
    return '*' * (len(word))

class BaseCaptionWriter:
    language_tag='en'
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.caption_counter = 0
        self.lines = []

    def segment_to_timed_words(self, json_segment):
        """Returns an array of word entries [ {"Duration":4900000, "Offset":8700000,"Word":"OK"}... """
        return json_segment["NBest"][0]['Words']
    
    def process_ms_json(self,json_results):
        """Returns a string - the json results converted into a webvtt or srt caption resource.
        language_tag must be a valid BCP47 language tag e.g. 'en' (English) 'de' (German) 'es' (Spanish). See https://tools.ietf.org/html/bcp47
        """
        timed_words = []
        for segment in json_results:
            timed_words.extend( self.segment_to_timed_words(segment))
            
        return self.process_timed_words(timed_words)
        
    def process_timed_words(self,timed_words):   
        self.reset()      
        self.emit_header()

        caption = None
        caption_start = 0
        caption_end = 0
        caption_line_length = 0 # Current line of caption (captions can have multiple lines)
        caption_line = 1
        num_words = len(timed_words)
    
        for ith, entry in enumerate(timed_words):
            try:
                # A tick represents one hundred nanoseconds, so convert to milliseconds
                # Mask profanity 
                duration, offset, word = int(entry['Duration']/1e4), int(entry['Offset']/1e4), mask_profanity(entry['Word']) # milliseconds
            except RuntimeError as re:
                print(re)
                # Ignore bad / missing word data
                continue
            
            is_last_few_words = (ith >= num_words - END_VIDEO_ORPHAN_COUNT)
          
            gap = offset - caption_end 
            new_caption_end = offset + duration
        
            # Can we just append the word to an existing caption line?
            if caption and (new_caption_end - caption_start <= MAX_CAPTION_DURATION_MS) and \
               (gap <= MAX_INTERWORD_GAP_MS) and \
               (caption_line_length + len(word) < MAX_CAPTION_CHAR_LENGTH_PER_LINE or caption_line < MAX_LINES_PER_CAPTION) and \
               (len(caption) < MAX_CAPTION_WORDS or is_last_few_words): 
                   if caption_line_length + len(word) > MAX_CAPTION_CHAR_LENGTH_PER_LINE:
                       caption.append('\n')
                       caption_line_length = len(word)
                       caption_line += 1
                   else:
                       caption_line_length += len(word) + 1
                   caption.append(word)
                   caption_end = new_caption_end
                   continue

            # If we get to here then we WILL be starting a new caption, but first check for a long gap and also emit current caption if it exists
            # Have we jumped forward in time? Emit a caption about the long gap in non-transcribed speech
            if gap > NOTABLE_SILENCE_MS:
                 self.emit(caption_end, offset,'[ Silence / Inaudible ]')  
                 caption_end = offset           
     
            if caption:
                # Emit current caption (with original end time)
                self.emit(caption_start, caption_end, ' '.join(caption))

            caption = [ word ]
            caption_line_length = len(word)
            caption_line = 1
         
            caption_start = offset
            if offset - caption_end < FUDGE_START_GAP_MS:
                caption_start = caption_end
            
            caption_end = new_caption_end

        # Clean up, we might still be building a caption after processing all of the words
        if caption:
             self.emit(caption_start, caption_end, ' '.join(caption))
         
        # Add acknowledgement if there were captions generated
        if caption_end > 0:
            caption_start = caption_end + ACKNOWLEDGEMENT_PRE_DELAY_MS
            caption_end = caption_start + ACKNOWLEDGEMENT_DURATION_MS
            self.emit(caption_start, caption_end,'[ ' + ACKNOWLEDGEMENT_TEXT1 + '\n' + ACKNOWLEDGEMENT_TEXT2+ ' ]' ) 
     
        return '\n'.join(self.lines)
            

class VTTCaptionWriter(BaseCaptionWriter):
    def __init__(self):
        pass
    
    def emit_header(self):
        self.lines.extend(['WEBVTT','Kind: Subtitles','Language: ' + self.language_tag])
        self.emit_note(ACKNOWLEDGEMENT_TEXT1 + ' ' + ACKNOWLEDGEMENT_TEXT2)        
   
    def to_timestamp(self,t_ms): 
        """Converts a millisecond time into a webvtt timestamp as a string e.g. 00:00.000 (times less than 1 hour) or 001:00:00.000 (at least 1 hour). Invalid (None or negative) are treated as a zero time value."""
        if t_ms is None or t_ms < 0:
            t_ms = 0
        
        t = int(t_ms/1000)
    
        hours = int(t / 3600)
        minutes = int(t / 60) % 60
        seconds = t % 60
        milli = int(t_ms) % 1000
    
        result = '{0:02d}:{1:02d}.{2:03d}'.format(minutes,seconds,milli)
        if hours == 0:
            return result # 09:59.000  # Minutes and seconds must be 2 digits. Milliseconds must be 3 digits
        else:
            return '{0:03d}:'.format(hours) + result # Hours value must never be 2 digits
    
    def write_start_end(self,start_ms, end_ms):
        """Creates a webvtt start-end time string e.g. 00:00.000 --> 00:01.000"""
        return '{0} --> {1}'.format(self.to_timestamp(start_ms), self.to_timestamp(end_ms))
    
    def emit(self,start,end,content):
         self.lines.extend([ self.write_start_end(start, end), content.replace('\n ','\n'), ''])
        
    def emit_note(self,content):
         self.lines.extend(['NOTE ' + content,''])
    
       
class SrtCaptionWriter(BaseCaptionWriter):
    def __init__(self):
        pass
    
    def emit_header(self):
        pass
        
    def emit(self,start,end,content):
        self.caption_counter =  self.caption_counter + 1
        self.lines.extend([str(self.caption_counter) , self.write_start_end(start, end), content.replace('\n ','\n'), ''])
        
    def emit_note(self,content):
        pass

    def to_timestamp(self,t_ms):
        """Converts a millisecond time into a srt timestamp as a string e.g. 00:00:00,000"""
        if t_ms is None or t_ms < 0:
            t_ms = 0
        
        t = int(t_ms/1000)
    
        hours = int(t / 3600)
        minutes = int(t / 60) % 60
        seconds = t % 60
        milli = int(t_ms) % 1000
    
        return '{0:02d}:{1:02d}:{2:02d},{3:03d}'.format(hours, minutes,seconds,milli)
    
    def write_start_end(self,start_ms, end_ms):
        """Returns a srt start-end time string e.g. 00:00,000 --> 00:01,000"""
        return '{0} --> {1}'.format( self.to_timestamp(start_ms), self.to_timestamp(end_ms))

class PlainTextWriter:
    def process_ms_json(self,json_results):
        """Extracts a simple text transcript using the Display property of the MS recognition json"""
        lines = []
        if not json_results:
            return '[ No speech found to transcribe ]'
        
        for segment in json_results:
            if segment['NBest']:
                try:
                    rawtext = segment['NBest'][0]['Display']
                    # Mask Profanity
                    word_array = re.split('(\W)', rawtext) # Keep delimiters e.g. periods, colons etc as their own entries in the array
                    # Put humpty *** dumpty together again, including original delimiters.
                    text = ''.join( [mask_profanity(w) for w in word_array ])
                except RuntimeError as err:
                    print(err)
                    text = '[ ???? ]'
            else:
                text = '[ Inaudible ]'
            
            
            lines.append(text)                 
        lines.extend(['','','# ' + ACKNOWLEDGEMENT_TEXT1,'# ' + ACKNOWLEDGEMENT_TEXT2])
        return '\n'.join(lines)

def main():
    if len(sys.argv) <3 :
        print ("Usage: {} input_json_file [output.txt]+ [output.vtt]+ [output.srt]+".format(sys.argv[0]) )
        print('Output format will be plain transcription text, srt captions, or webvtt captions depending on file extension (.txt .srt or .vtt)')
        print('More than one output file can be specified')
        sys.exit(1)
        
    json_file = sys.argv[1]
    
    with open(json_file, 'r') as in_file:
        json_text = in_file.read()
    
    json_results = json.loads(json_text)
     
    language_tag = 'en'
    
    for caption_file in sys.argv[2:]:
        caption_type = os.path.splitext(caption_file)[1][1:]     
        
        captioner = None
        if( caption_type == 'txt'):
            captioner = PlainTextWriter()
        elif( caption_type == 'vtt'):
            captioner = VTTCaptionWriter()
        elif( caption_type == 'srt'):
            captioner = SrtCaptionWriter()
        else:
            print('Unrecognized caption format:\''+kind+'\'. Only txt, vtt or srt captions are supported')
            sys.exit(1)
    
        captions = captioner.process_ms_json(json_results)
    
        with open(caption_file, 'w') as out_file:
            out_file.write(captions)
    sys.exit(0)
   

if __name__== "__main__":
    main()

