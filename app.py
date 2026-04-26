import os
import json
import asyncio
import streamlit as st
from moviepy.editor import *
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Safe import
try:
    import edge_tts
    EDGE_AVAILABLE = True
except:
    EDGE_AVAILABLE = False

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.title("🎬 Training Recap Video Generator (Generic + Complete)")

uploaded_files = st.file_uploader(
    "Upload transcripts",
    type=["txt"],
    accept_multiple_files=True
)

# ---------- REMOVE SPEAKER ----------
def remove_speaker(text, speaker="Ravi"):
    return "\n".join([
        l for l in text.split("\n")
        if not l.strip().lower().startswith(
            (speaker.lower()+":", speaker.lower()+" -", speaker.lower()+"(")
        )
    ])

# ---------- ADD PAUSES ----------
def add_pauses(text):
    text = text.replace(".", ". ")
    text = text.replace(",", ", ")
    return text

# ---------- GENERATE STRUCTURED SLIDES ----------
def generate_structured_slides(full_text):
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": f"""
Create structured recap slides.

Return JSON:
{{
  "slides": [
    {{
      "title": "Exact topic name",
      "points": ["point1", "point2", "point3", "point4"],
      "narration": "detailed explanation"
    }}
  ]
}}

RULES:
- Maintain original order
- Each topic must be separate
- Do NOT miss technical concepts
- Keep exact terms (no renaming)

SLIDES:
- 4–6 bullet points

NARRATION:
- 6–8 short sentences
- Include explanation + example

Avoid: speaker, lecture, session, today

Text:
{full_text[:12000]}
"""
        }]
    )

    return json.loads(res.choices[0].message.content)["slides"]

# ---------- EXTRACT KEY TOPICS ----------
def extract_key_terms(full_text):
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": f"""
Extract important technical topics.

Return JSON:
{{ "topics": ["topic1", "topic2"] }}

Rules:
- Include ALL important terms
- Keep exact names (vector database, embeddings, etc.)
- No generalization

Text:
{full_text[:8000]}
"""
        }]
    )

    return json.loads(res.choices[0].message.content)["topics"]

# ---------- ENSURE ALL TOPICS INCLUDED ----------
def ensure_key_topics(slides, key_topics):
    existing_titles = [s["title"].lower() for s in slides]

    for topic in key_topics:
        if not any(topic.lower() in t for t in existing_titles):

            slides.append({
                "title": topic,
                "points": [
                    f"{topic} concept overview",
                    "Used in practical applications",
                    "Important in system design",
                    "Common in real-world scenarios"
                ],
                "narration": f"{topic} was also covered. It is an important concept. It is used in practical applications. This helps improve system design and performance."
            })

    return slides

# ---------- ADD SUMMARY ----------
def add_summary_slide(slides):
    topics = [s["title"] for s in slides[:8]]

    slides.append({
        "title": "Key Topics Covered",
        "points": topics[:6],
        "narration": "The recap covered key topics including " + ", ".join(topics[:6]) + ". This provided a structured understanding of the overall concepts."
    })

    return slides

# ---------- AUDIO ----------
def generate_audio(slides):
    files = []

    async def edge_generate(text, filename):
        communicate = edge_tts.Communicate(
            text=text,
            voice="en-US-AriaNeural",
            rate="+0%",
            pitch="+0Hz"
        )
        await communicate.save(filename)

    for i, slide in enumerate(slides):
        fname = f"audio_{i}.mp3"
        text = add_pauses(slide["narration"])

        try:
            if EDGE_AVAILABLE:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(edge_generate(text, fname))
                loop.close()
            else:
                raise Exception()

        except:
            from gtts import gTTS
            gTTS(text).save(fname)

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

    w = draw.textbbox((0,0), lines[0], font=title_font)[2]
    draw.text(((1280-w)//2,80), lines[0], font=title_font, fill=(0,0,0))

    y = 180
    for l in lines[1:]:
        draw.text((100,y), l, font=body_font, fill=(0,0,0))
        y += 40

    return np.array(img)

# ---------- VIDEO ----------
def create_video(slides, audio_files):
    clips, audios = [], []

    for i, slide in enumerate(slides):
        text = slide["title"] + "\n\n" + "\n".join([f"• {p}" for p in slide["points"]])

        img = create_slide(text)
        audio = AudioFileClip(audio_files[i])

        extra_time = 2.0
        clip = ImageClip(img).set_duration(audio.duration + extra_time)
        clip = clip.fadein(0.4).fadeout(0.4)

        clips.append(clip)
        audios.append(audio)

    video = concatenate_videoclips(clips, method="compose")
    audio = concatenate_audioclips(audios)

    video = video.set_audio(audio)

    video.write_videofile(
        "final_video.mp4",
        fps=24,
        codec="libx264",
        audio_codec="aac",
        audio_bitrate="192k"
    )

    return "final_video.mp4"

# ---------- MAIN ----------
if uploaded_files:
    if st.button("Generate Recap Video"):
        try:
            full_text = ""

            for f in uploaded_files:
                text = f.read().decode("utf-8")
                text = remove_speaker(text, "Ravi")
                full_text += "\n\n" + text

            slides = generate_structured_slides(full_text)

            key_topics = extract_key_terms(full_text)
            slides = ensure_key_topics(slides, key_topics)
            slides = add_summary_slide(slides)

            audio_files = generate_audio(slides)
            video = create_video(slides, audio_files)

            st.success("✅ Video Ready")
            st.video(video)

        except Exception as e:
            st.error(str(e))
