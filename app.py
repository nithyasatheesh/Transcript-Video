import os
import json
import re
import streamlit as st
from moviepy.editor import *
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Voice setup
USE_ELEVENLABS = os.getenv("ELEVEN_API_KEY") is not None
if USE_ELEVENLABS:
    from elevenlabs import generate, save, set_api_key
    set_api_key(os.getenv("ELEVEN_API_KEY"))
else:
    from gtts import gTTS

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.title("🎬 Training Recap Video Generator")

uploaded_files = st.file_uploader(
    "Upload daily transcripts",
    type=["txt"],
    accept_multiple_files=True
)

# -------- SAFE JSON --------
def safe_json_load(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(match.group())

# -------- DAILY SUMMARY --------
def summarize_day(transcript):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[{
            "role": "user",
            "content": f"""
Summarize this training content.

Focus on:
- Key topics
- Outcomes
- Keep concise

Text:
{transcript[:6000]}
"""
        }]
    )
    return response.choices[0].message.content

# -------- MODULE RECAP --------
def generate_module_recap(day_summaries):
    combined = "\n\n".join(day_summaries)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        messages=[{
            "role": "user",
            "content": f"""
Create a simple professional recap.

STRICT:
- Do NOT use: speaker, lecture, session
- Use simple corporate language

Style:
- The training started with...
- Key topics included...
- The focus then moved to...
- Important areas covered were...
- The program concluded with...

Content:
{combined}
"""
        }]
    )

    return response.choices[0].message.content

# -------- CLEAN TEXT --------
def clean_text(text):
    banned = ["speaker", "lecture", "session"]
    for word in banned:
        text = text.replace(word, "")
    return text

# -------- SEGMENTS --------
def split_into_segments(summary):
    sentences = summary.split(". ")
    segments = []
    current = ""

    for s in sentences:
        if len(current.split()) < 45:
            current += s + ". "
        else:
            segments.append(current.strip())
            current = s + ". "

    if current:
        segments.append(current.strip())

    return segments

# -------- BUILD SLIDE + NARRATION (KEY FIX) --------
def build_slide_content(segments):
    slides = []

    for seg in segments:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": f"""
Create slide and narration from this.

Return JSON:
{{
  "title": "Short title",
  "points": ["short point", "short point"],
  "narration": "spoken version of same content"
}}

Rules:
- Max 3 bullets
- Simple wording
- Narration MUST match slide content

Text:
{seg}
"""
            }]
        )

        slides.append(safe_json_load(response.choices[0].message.content))

    return slides

# -------- AUDIO --------
def generate_audio_from_slides(slides):
    files = []

    for i, slide in enumerate(slides):
        text = slide["narration"]
        fname = f"audio_{i}.mp3"

        if USE_ELEVENLABS:
            audio = generate(
                text=text,
                voice="Rachel",
                model="eleven_multilingual_v2"
            )
            save(audio, fname)
        else:
            tts = gTTS(text, slow=False)
            tts.save(fname)

        files.append(fname)

    return files

# -------- IMAGE --------
def create_text_image(text):
    img = Image.new("RGB", (1280, 720), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    base_dir = os.path.dirname(__file__)
    title_font_path = os.path.join(base_dir, "fonts", "DejaVuSans-Bold.ttf")
    body_font_path = os.path.join(base_dir, "fonts", "DejaVuSans.ttf")

    try:
        title_font = ImageFont.truetype(title_font_path, 55)
        body_font = ImageFont.truetype(body_font_path, 20)
    except:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    lines = text.split("\n")

    bbox = draw.textbbox((0, 0), lines[0], font=title_font)
    text_width = bbox[2] - bbox[0]
    draw.text(((1280 - text_width)//2, 80), lines[0], font=title_font, fill=(0,0,0))

    y = 180
    for line in lines[1:]:
        draw.text((100, y), line, font=body_font, fill=(0,0,0))
        y += 40

    return np.array(img)

# -------- VIDEO --------
def create_video(slides, audio_files):
    clips = []
    audio_clips = []
    current_time = 0

    for i, slide in enumerate(slides):
        text = slide["title"] + "\n\n" + "\n".join([f"• {p}" for p in slide["points"]])

        img = create_text_image(text)
        audio = AudioFileClip(audio_files[i])

        clip = ImageClip(img).set_start(current_time).set_duration(audio.duration)

        clips.append(clip)
        audio_clips.append(audio)

        current_time += audio.duration

    final_audio = concatenate_audioclips(audio_clips)

    total_duration = final_audio.duration
    if total_duration < 180:
        factor = 180 / total_duration
        clips = [c.set_duration(c.duration * factor) for c in clips]

    video = CompositeVideoClip(clips).set_audio(final_audio)

    video.write_videofile(
        "final_video.mp4",
        fps=24,
        codec="libx264",
        audio_codec="aac"
    )

    return "final_video.mp4"

# -------- MAIN --------
if uploaded_files:
    if st.button("Generate Recap Video"):
        try:
            day_summaries = []

            with st.spinner("Processing transcripts..."):
                for f in uploaded_files:
                    text = f.read().decode("utf-8")
                    day_summaries.append(summarize_day(text))

            recap = generate_module_recap(day_summaries)
            recap = clean_text(recap)

            st.subheader("📄 Recap")
            st.write(recap)

            segments = split_into_segments(recap)

            slides = build_slide_content(segments)  # 🔥 key fix
            audio_files = generate_audio_from_slides(slides)

            video = create_video(slides, audio_files)

            st.success("✅ Video Ready!")
            st.video(video)

        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
