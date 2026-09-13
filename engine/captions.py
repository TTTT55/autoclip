import os, re

def ass_time(seconds):
    seconds=max(0,float(seconds)); h=int(seconds//3600); m=int((seconds%3600)//60); s=int(seconds%60); cs=int((seconds%1)*100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def write_ass(words, output, style="word_pop"):
    primary = "&H00FFFFFF"; highlight="&H0000FFFF"
    lines=["[Script Info]","ScriptType: v4.00+","PlayResX: 1080","PlayResY: 1920",
           "[V4+ Styles]","Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Alignment, MarginL, MarginR, MarginV, Encoding",
           f"Style: Default,Arial,64,{primary},&H00000000,&H00000000,&H99000000,1,0,5,60,60,220,1",
           "[Events]","Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for i,w in enumerate(words):
        start=w["start"]; end=w["end"]
        text=w["text"].replace("{","").replace("}","")
        if style=="word_pop":
            text=f"{{\\c{highlight}}}{text}{{\\c{primary}}}"
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}")
    with open(output,"w",encoding="utf-8") as f: f.write("\n".join(lines))
    return output

def words_for_range(words,start,end):
    return [w for w in words if w["end"] >= start and w["start"] <= end]
