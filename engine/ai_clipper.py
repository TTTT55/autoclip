import json, os
from openai import OpenAI

def select_clips(transcript, max_clips=5, min_duration=20, max_duration=60):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for AI clip selection")
    client = OpenAI(api_key=api_key)
    prompt = f"""You are an expert short-form video editor. Find the {max_clips} strongest self-contained moments in this transcript.
Prefer hooks, surprising insights, stories, humor, emotion, useful advice, controversy, and clear payoffs. Avoid introductions, ads, incomplete thoughts and overlapping clips.
Each clip must be {min_duration}-{max_duration} seconds and begin/end on natural sentence boundaries.
Return ONLY JSON: {{"clips":[{{"start_word":0,"end_word":10,"score":0,"title":"","hook":"","reason":""}}]}}.
score is 0-100. Use transcript word indexes, not guessed seconds.

TRANSCRIPT WORDS:
{json.dumps([{"i":i,"text":w["text"]} for i,w in enumerate(transcript["words"])], ensure_ascii=False)}
"""
    r = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.2,
        response_format={"type":"json_object"},
        messages=[{"role":"system","content":"Return valid JSON only."},{"role":"user","content":prompt}]
    )
    data=json.loads(r.choices[0].message.content)
    words=transcript["words"]
    clips=[]
    for c in data.get("clips", []):
        s=max(0,min(len(words)-1,int(c["start_word"])))
        e=max(s,min(len(words)-1,int(c["end_word"])))
        text=" ".join(w["text"] for w in words[s:e+1])
        clips.append({**c,"start":words[s]["start"],"end":words[e]["end"],"transcript":text})
    return clips
