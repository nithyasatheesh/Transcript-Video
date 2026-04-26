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

st.title("🎬 Session Recap Video Generator")

uploaded_file = st.file_uploader("Upload transcript (.txt)", type=["txt"])


# -------- SAFE JSON --------
def safe_json_load(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(match.group())


# -------- RECAP SUMMARY (PAST TENSE) --------
def generate_summary(transcript):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        messages=[
            {
                "role": "user",
                "content": f"""
Create a recap of this session in PAST TENSE.

IMPORTANT:
- Use past tense only (covered, discussed, explained)
- Do NOT use present tense

Style:
- Start with: "In this session, we covered..."
- Then continue with:
  "We discussed..."
  "Then we explored..."
  "After that, we looked at..."
  "Finally, we concluded..."

Tone:
- Natural
- Smooth storytelling
- Like summarizing a completed lecture

Keep it suitable for 3–5 minute narration.

Transcript:
{transcript[:8000]}
"""
            }
        ]
    )
    return response.choices[0].message.content


# -------- FORCE PAST TENSE (SAFETY) --------
def enforce_past_tense(text):
    replacements = {
        "we discuss": "we discussed",
        "we explain": "we explained",
        "we explore": "we explored",
        "we look at": "we looked at",
        "we cover": "we covered",
        "we learn": "we learned",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text


# -------- SLIDES --------
def generate_slides(summary):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": f"""
Convert this recap into slides.

Return JSON:
{{
  "slides": [
    {{
      "title": "Short title",
      "points": ["short point", "short point"]
    }}
  ]
}}

Rules:
- 6–8 slides
- Max 3 bullet points
- VERY short text (keywords only)

Recap:
{summary}
"""
            }
        ]
    )
    return response.choices[0].message.content


# -------- SLOW SCRIPT --------
def slow_script(script):
    return script.replace(".", ". ... ")


# -------- AUDIO --------
def text_to_audio(script):
    script = slow_script(script)

    if USE_ELEVENLABS:
        audio = generate(
            text=script,
            voice="Rachel",
            model="eleven_multilingual_v2"
        )
        save(audio, "audio.mp3")
    else:
        tts = gTTS(script)
        tts.save("audio.mp3")

    return "audio.mp3"


# -------- SLIDE IMAGE --------
def create_text_image(text):
    img = Image.new("RGB", (1280, 720), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    base_dir = os.path.dirname(__file__)
    title_font_path = os.path.join(base_dir, "fonts", "DejaVuSans-Bold.ttf")
    body_font_path = os.path.join(base_dir, "fonts", "DejaVuSans.ttf")

    try:
        title_font = ImageFont.truetype(title_font_path, 60)
        body_font = ImageFont.truetype(body_font_path, 30)
    except:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    lines = text.split("\n")

    # Center title
    bbox = draw.textbbox((0, 0), lines[0], font=title_font)
    text_width = bbox[2] - bbox[0]
    draw.text(((1280 - text_width) // 2, 80), lines[0], font=title_font, fill=(0, 0, 0))

    # Bullets
    y = 300
    for line in lines[1:]:
        draw.text((120, y), line, font=body_font, fill=(0, 0, 0))
        y += 140

    return np.array(img)


# -------- VIDEO --------
def create_video(slides_json, audio_file):
    data = safe_json_load(slides_json)
    slides = data["slides"]

    audio = AudioFileClip(audio_file).set_fps(44100)

    total_duration = audio.duration
    slide_duration = total_duration / len(slides)

    clips = []

    for slide in slides:
        text = slide["title"] + "\n\n" + "\n".join([f"• {p}" for p in slide["points"]])

        img = create_text_image(text)
        clip = ImageClip(img).set_duration(slide_duration)

        clips.append(clip)

    video = concatenate_videoclips(clips).set_audio(audio)

    video.write_videofile(
        "final_video.mp4",
        fps=24,
        codec="libx264",
        audio_codec="aac"
    )

    return "final_video.mp4"


# -------- MAIN --------
if uploaded_file:
    transcript = uploaded_file.read().decode("utf-8")

    if st.button("Generate Recap Video"):
        try:
            with st.spinner("Generating recap..."):
                summary = generate_summary(transcript)
                summary = enforce_past_tense(summary)

            st.subheader("📄 Recap")
            st.write(summary)

            with st.spinner("Creating video..."):
                slides_json = generate_slides(summary)

                audio = text_to_audio(summary)  # narration = recap
                video = create_video(slides_json, audio)

            st.success("✅ Video Ready!")
            st.video(video)

        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
