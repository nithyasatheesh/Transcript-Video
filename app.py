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

st.title("🎬 Module Recap Video Generator")

uploaded_files = st.file_uploader(
    "Upload multiple transcripts (4–5 days)",
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
Summarize this lecture briefly (5–6 lines max).

Transcript:
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
Create a recap of a module in past tense.

Do NOT use "In this session".

Style:
- The lecture began with...
- Then we discussed...
- Later the focus shifted...
- Finally...

Make it smooth and natural (3–5 min narration).

Summaries:
{combined}
"""
        }]
    )
    return response.choices[0].message.content


# -------- SEGMENT SPLIT --------
def split_into_segments(summary):
    sentences = summary.split(". ")
    segments = []
    current = ""

    for s in sentences:
        if len(current.split()) < 40:
            current += s + ". "
        else:
            segments.append(current.strip())
            current = s + ". "

    if current:
        segments.append(current.strip())

    return segments


# -------- SLIDES --------
def generate_slides(segments):
    slides = []

    for seg in segments:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": f"""
Create ONE slide.

Return JSON:
{{
  "title": "Short title",
  "points": ["short point", "short point"]
}}

Max 3 points. Keep very short.

Text:
{seg}
"""
            }]
        )

        slides.append(safe_json_load(response.choices[0].message.content))

    return slides


# -------- AUDIO --------
def text_to_audio(text, filename):
    if USE_ELEVENLABS:
        audio = generate(
            text=text,
            voice="Rachel",
            model="eleven_multilingual_v2"
        )
        save(audio, filename)
    else:
        tts = gTTS(text, slow=False)
        tts.save(filename)

    return filename


def generate_audio_segments(segments):
    files = []
    for i, seg in enumerate(segments):
        fname = f"audio_{i}.mp3"
        files.append(text_to_audio(seg, fname))
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

    # Title
    bbox = draw.textbbox((0, 0), lines[0], font=title_font)
    text_width = bbox[2] - bbox[0]
    draw.text(((1280 - text_width)//2, 60), lines[0], font=title_font, fill=(0,0,0))

    # Bullets
    y = 200
    for line in lines[1:]:
        draw.text((120, y), line, font=body_font, fill=(0,0,0))
        y += 90

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
    if st.button("Generate Module Recap Video"):
        try:
            day_summaries = []

            with st.spinner("Summarizing days..."):
                for f in uploaded_files:
                    text = f.read().decode("utf-8")
                    day_summaries.append(summarize_day(text))

            st.subheader("📄 Daily Summaries")
            for i, d in enumerate(day_summaries):
                st.write(f"Day {i+1}: {d}")

            with st.spinner("Generating recap..."):
                recap = generate_module_recap(day_summaries)

            st.subheader("🎯 Module Recap")
            st.write(recap)

            segments = split_into_segments(recap)
            slides = generate_slides(segments)
            audio_files = generate_audio_segments(segments)
            video = create_video(slides, audio_files)

            st.success("✅ Video Ready!")
            st.video(video)

        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
