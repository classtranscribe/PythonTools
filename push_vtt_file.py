import socket
import datetime
import re
import time

#https://stackoverflow.com/questions/54371492/changing-the-format-of-timestamp-in-python-3-7

def to_timedelta(t):
    timept = re.split(r'[:.]+', t)
    h, m, s, ss = list(map(int, timept))
    return datetime.timedelta(hours=h, minutes=m, seconds=s, milliseconds=ss)

def select(cues,currenttime,prevtime):
    return  [ c for c in cues if c['start'] >  prevtime and c['start'] <=  currenttime ]

def unescape(s):
    return s.replace('&lt;','<').replace('&gt;','>').replace('&quot','"').replace('&apos',"'").replace('&amp;','&')


def read_caption_file(vttfile):
    #https://stackoverflow.com/questions/48640490/python-2-7-matching-a-subtitle-events-in-vtt-subtitles-using-a-regular-expressi
    regex = re.compile(r"""(^[0-9]{2}[:][0-9]{2}[:][0-9]{2}[.,][0-9]{3})   # match TC-IN in group1
                             [ ]-->[ ]                                     # VTT/SRT style TC-IN--TC-OUT separator
                             ([0-9]{2}[:][0-9]{2}[:][0-9]{2}[.,][0-9]{3})  # match TC-OUT n group2
                             (.*)\r?\n([\s\S]*?)\s*(?:(?:\r?\n){2}|\Z) # additional VTT info (like) alignment
                                                             
                                                            # subtitle_content """, re.MULTILINE|re.VERBOSE)
    
    with open(vttfile, 'r', encoding = 'utf-8') as webvttFileObject:
        vttcontent = webvttFileObject.read()
    cues = []
    for match in regex.finditer(vttcontent):
        group1, group2, group3, group4 = match.groups()
        tc_in = to_timedelta( group1.strip())
        tc_out = to_timedelta( group2.strip())
        vtt_extra_info = group3
        text = group4
        cue = dict()
        cue = {'start': tc_in, 'end':tc_out,'extra':vtt_extra_info,'text': unescape(text)}
        cues.append(cue)
    return cues

def select(cues, elapsed, cutoff):
    result = [ c for c in cues if elapsed >= c['start'] and cutoff <  c['start'] ]
    return result
    
def cue_start_end(cues):
    if len(cues) == 0:
        return datetime.timedelta()
    return cues[0]['start'], cues[-1]['end']

def connect_encoder(host, port,channel):
    if host and port and channel in '12':
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, int(port))) # connect to link encoder using the specified credentials
        fieldinsertmode = {'1' : b"\x01\x33\x0D" * 2, '2': b"\x01\x34\x0D" * 2 } [ str(channel)]
        rollupcode = b"\x14\x2D\x14\x70"
        s.sendall(fieldinsertmode + rollupcode)
        text = bytes("Captions by CT-Cast\n", "iso-8859-1")
        s.sendall(fieldinsertmode + rollupcode4 + text)
        return s
    else:
        print("Dry run; host, port and channel must be specified")
        return None

def send_cues(cues, connection):
    shortwords = []
    for c in cues:
        lines = c['text'].split('\n')
        for line in lines:
            words = line.split(' ')
            print(c['start'], words)
            # Cheap split
            MAX_LEN = 32
            for word in words:
                while(len(word)):                
                    if len(word) <= MAX_LEN:
                        shortwords.append(word)
                        break
                    shortwords.append(word[0:MAX_LEN -1] + '-')
                    word = word[MAX_LEN:]
            shortwords.append('\n')
    print()
    lines = ['']
    for word in shortwords:
        if word == '\n':
            lines.append('')
            continue
        candidate = lines[-1]
        if len(candidate) > 0:
            candidate += ' '
        candidate += word
        if len( candidate ) <= MAX_LEN:
            lines[-1] = candidate
        else:
            lines.append(word)
    one_line = '\n'.join(lines).replace('\n\n','\n')
    #print('Raw text')
    #print( one_line)
 
    if connection:
        raw_text = bytes(one_line, "iso-8859-1")
        connection.sendall(raw_text)
    
def main():
    vttfilename = 'ex.vtt'
    dry_run = True
    speed_factor = 2
    
    channel = 1
    host = None
    port = None

    all_cues = read_caption_file(vttfilename)
    
    first_cue_at,cues_finish_at = cue_start_end(all_cues)
    print(f"{len(all_cues)} cues read. First queue at {first_cue_at}, ending at {cues_finish_at}")

    connection = connect_encoder(host,port, channel)
    
    previous_elapsed = datetime.timedelta(seconds = -1)
    start_clock_time = datetime.datetime.now()

    while(True):
        elapsed = datetime.datetime.now() - start_clock_time
        elapsed *= speed_factor
        if elapsed >= cues_finish_at:
            break
            
        cues = select(all_cues, elapsed, previous_elapsed)
        previous_elapsed = elapsed
        if len(cues) > 0:
            send_cues(cues, connection)
        time.sleep(1)
    print("Finished")

if __name__ == '__main__':
    main()
