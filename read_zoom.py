# A utility to convert text transcriptions from Zoom to vtt and srt caption files

# The MIT License (MIT)

# Copyright © 2021 Lawrence Angrave

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


# Apparent input format-
#    A line either starts with a clock time HH:MM:SS or is a continuation of a caption text or is a blank line. There may be caption text after the timestamp.
#    Some lines have speaker identification in the format >> NAME: sometimes with the colon, sometimes not. There may be text after that on the same line. Some speaker identifications don't have the >> characters

# This utility also assumes long gaps correspond to paused video recordings

import os
import sys
import re
import datetime


def to_timedelta(t):
    remain = ""
    if " " in t:
        t, remain = t.split(" ", 1)
    timept = re.split(r"[:]+", t, 3)
    h, m, s = list(map(int, timept))
    return datetime.timedelta(hours=h, minutes=m, seconds=s), remain

# We have to manually specify how long the last caption should be displayed for
last_caption_duration = datetime.timedelta(seconds=2)

# If captions have the same start time then delay a caption so the current caption has at least some display time
min_display_time = datetime.timedelta(seconds=1)

# Long gaps are assumed to be pauses in the recording
skip_long_gap_threshold = datetime.timedelta(minutes=5)

# Long gaps are replaced with this duration
shortened_gap_duration = datetime.timedelta(seconds=1)



def read_file_as_lines(filename):
    """Reads the text file as utf-8 and returns an array of lines, dropping all newline and CR characters"""
    with open(filename, "r", encoding="utf-8") as f:
        filelines = [line.replace("\r", "").rstrip("\n") for line in f.readlines()]
    return filelines


def parse(rawlines, starting_time):
    """Parses Zoom transcriptions. Lines may start with a timestamp - the current time. The general plan is to build up the current caption line and append it to the list of captions parsed so far. The starting_time allows captions to be offset from the video recording."""
    captions = []
    start = None
    text = None

    for line in rawlines:
        if len(line) == 0:
            continue
        if line[0].isdigit():
            newstart, newtext = to_timedelta(line)
            if starting_time is None:
                starting_time = newstart
            newstart -= starting_time

            if text is not None and len(text) > 0:
                duration = newstart - start
                if (
                    duration >= skip_long_gap_threshold
                    and newstart.total_seconds() >= 0
                ):
                    adjusted_duration = shortened_gap_duration
                    time_shift = duration - adjusted_duration
                    print(
                        f"Timeshifting by {time_shift} long gap at input {newstart + starting_time}. {duration}-> {adjusted_duration} duration. {newstart} back to {newstart - time_shift} "
                        + text.replace("\n", " ")[:40]
                    )
                    duration = adjusted_duration
                    starting_time += time_shift
                    newstart -= time_shift

                # Occasionally two Zoom captions can have the same time, which would mean
                # the first caption would be displayed for zero seconds
                # To prevent this we require captions to be displayed for a minimun time
                # delaying the start of the next caption by the same amount
                # Future Alternative: Concatenate the caption lines together into a single cue if both are single line
                if duration < min_display_time:
                    duration = min_display_time

                captions.append({"start": start, "end": start + duration, "text": text})
            start = newstart
            text = newtext.strip()

        else:
            assert start is not None
            line = line.strip()
            if len(line) > 0:
                text += ("\n" if len(text) > 0 else "") + line
    if text:
        captions.append(
            {"start": start, "end": start + last_caption_duration, "text": text}
        )

    captions = [c for c in captions if c["start"].total_seconds() >= 0]
    return captions


def toCueTime(t, sep=","):
    """Return a srt or vtt timestamp string e.g. 12:34:56,000 (srt) 12:34:56.000 (vtt)"""
    s = int(t.seconds)
    assert s >= 0
    milli = int(1000 * (t.seconds - s))
    return f"{s//3600:02}:{s//60%60:02}:{s%60:02}{sep}{milli:03}"


def export(out, captions, output_format="srt"):
    """Saves the parsed captions in various formats to the given output stream"""
    if output_format == "srt":
        sep = ","
    elif output_format == "vtt":
        sep = "."
        print("WEBVTT\nKind: captions\nLanguage: en\n", file=out)
    else:
        raise Exception(f"Expected format of vtt or srt, got:{output_format}")

    for idx, cue in enumerate(captions, start=1):
        start, end = toCueTime(cue["start"], sep), toCueTime(cue["end"], sep)
        text = cue["text"]

        text = text.replace("&", "&amp;").replace(">", "&gt;").replace("<", "&lt;")

        if output_format == "srt":
            print(idx, file=out)

        print(f"{start} --> {end}", file=out)
        print(text, file=out)
        print("", file=out)


def usage():
    usage = """Example usage: python3 NAME '08:02:33' zoom1.txt
    Will generate an output file zoom1.vtt
    srt output format is also supported"""

    print(usage.replace("NAME", sys.argv[0]))


def main():
    """Main entry point"""
    if len(sys.argv) not in [2, 3]:
        usage()
        return 1

    #e.g. '08:02:33'

    # Did the user give us a timestamp?
    arg = sys.argv[1]
    if len(arg) == 8 and re.match(r"[0-9][0-9]:[0-9][0-9]:[0-9][0-9]", arg):
        starting_time, _ = to_timedelta(arg)
        print("Starting_time:", starting_time)
        input_file = sys.argv[2]
    else:
        starting_time = None
        input_file = arg

    if not input_file.endswith(".txt"):
        print(f"Input file,{input_file}, must end with a .txt extension")
        return 3

    if not os.path.exists(input_file):
        print(f"Input file '{input_file}' does not exist", file=sys.stderr)
        return 3

    # if os.path.exists(output_file):
    #    print(f"Skipping '{input_file}'; '{output_file}' already exists")
    #    return 4

    raw_lines = read_file_as_lines(input_file)
    captions = parse(raw_lines, starting_time)

    for output_format in ["srt", "vtt"]:
        output_file = input_file.rsplit(".", 1)[0] + "." + output_format
        assert output_file != input_file

        print(f"Writing {output_format} to '{output_file}'")
        with open(output_file, "w", encoding="utf-8") as out:
            export(out, captions, output_format)

    print(f"{len(captions)} captions written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
