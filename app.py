import os
import json
import streamlit as st
from moviepy.editor import *
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# ---------- SETUP ----------
USE_ELEVENLABS = os.getenv("ELEVEN_API_KEY") is not None
if USE_ELEVENLABS:
    from elevenlabs import generate, save, set_api_key
    set_api_key(os.getenv("ELEVEN_API_KEY"))
else:
    from gtts import gTTS

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.title("🎬 Training Recap Video Generator (Full Coverage)")

uploaded_files = st.file_uploader(
    "Upload transcripts",
    type=["txt"],
    accept_multiple_files=True
)

# ---------- REMOVE RAVI ----------
def remove_speaker(text, speaker="Ravi"):
    lines = text.split("\n")
    return "\n".join([
        l for l in lines
        if not l.strip().lower().startswith(
            (speaker.lower()+":", speaker.lower()+" -", speaker.lower()+"(")
        )
    ])

# ---------- EXTRACT TOPICS ----------
def extract_topics(text):
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": f"""
Extract ALL key topics.

Return JSON:
{{ "topics": ["topic1", "topic2"] }}

Do NOT miss any important topic.

Text:
{text[:8000]}
"""
        }]
    )
    return json.loads(res.choices[0].message.content)["topics"]

# ---------- EXPAND TOPICS ----------
def expand_topics(topics):
    slides = []

    for topic in topics:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": f"""
Create slide + narration.

Return JSON:
{{
"title": "{topic}",
"points": ["short point", "short point"],
"narration": "2-3 sentence explanation"
}}

Keep simple corporate language.
Narration must match slide.

Topic:
{topic}
"""
            }]
        )

        slides.append(json.loads(res.choices[0].message.content))

    return slides

# ---------- AUDIO ----------
def generate_audio(slides):
    files = []

    for i, s in enumerate(slides):
        fname = f"audio_{i}.mp3"
        text = s["narration"]

        try:
            if USE_ELEVENLABS:
                audio = generate(text=text, voice="Rachel")
                save(audio, fname)
            else:
                gTTS(text, slow=False).save(fname)

            # speed up
            clip = AudioFileClip(fname)
            fast = clip.fx(vfx.speedx, 1.2)
            fast_name = f"fast_{i}.mp3"
            fast.write_audiofile(fast_name)

            files.append(fast_name)

        except:
            gTTS("Overview.", slow=False).save(fname)
            files.append(fname)

    return files

# ---------- IMAGE ----------
def create_slide(text):
    img = Image.new("RGB", (1280,720), (255,255,255))
    draw = ImageDraw.Draw(img)

    base = os.path.dirname(__file__)
    try:
        title_font = ImageFont.truetype(os.path.join(base,"fonts/DejaVuSans-Bold.ttf"),55)
        body_font = ImageFont.truetype(os.path.join(base,"fonts/DejaVuSans.ttf"),20)
    except:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    lines = text.split("\n")

    w = draw.textbbox((0,0),lines[0],font=title_font)[2]
    draw.text(((1280-w)//2,80),lines[0],font=title_font,fill=(0,0,0))

    y=180
    for l in lines[1:]:
        draw.text((100,y),l,font=body_font,fill=(0,0,0))
        y+=40

    return np.array(img)

# ---------- VIDEO ----------
def create_video(slides, audio_files):
    clips, audios = [], []

    for i, s in enumerate(slides):
        text = s["title"] + "\n\n" + "\n".join([f"• {p}" for p in s["points"]])
        img = create_slide(text)
        audio = AudioFileClip(audio_files[i])

        clip = ImageClip(img).set_duration(audio.duration)
        clip = clip.fadein(0.3).fadeout(0.3)

        clips.append(clip)
        audios.append(audio)

    video = concatenate_videoclips(clips, method="compose")
    audio = concatenate_audioclips(audios)

    video = video.set_audio(audio)

    # ensure 3–5 mins
    dur = audio.duration
    if dur < 180:
        video = video.fx(vfx.speedx, dur/180)
    elif dur > 300:
        video = video.fx(vfx.speedx, dur/300)

    video.write_videofile(
        "final_video.mp4",
        fps=24,
        codec="libx264",
        audio_codec="aac"
    )

    return "final_video.mp4"

# ---------- MAIN ----------
if uploaded_files:
    if st.button("Generate Full Recap Video"):
        try:
            all_topics = []

            for f in uploaded_files:
                text = f.read().decode("utf-8")
                text = remove_speaker(text, "Ravi")

                topics = extract_topics(text)
                all_topics.extend(topics)

            # remove duplicates
            all_topics = list(dict.fromkeys(all_topics))

            st.write("### Extracted Topics")
            st.write(all_topics)

            slides = expand_topics(all_topics)
            audio_files = generate_audio(slides)

            video = create_video(slides, audio_files)

            st.success("✅ Video Ready")
            st.video(video)

        except Exception as e:
            st.error(str(e))
