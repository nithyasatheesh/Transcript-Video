import os
import json
import re
import streamlit as st
from gtts import gTTS
from moviepy.editor import *
from openai import OpenAI
import requests

# Init OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.set_page_config(page_title="Slide Video Generator")

st.title("🎬 AI Slide Video Generator")
st.write("Upload transcript → get slide-based recap video")

uploaded_file = st.file_uploader("Upload transcript (.txt)", type=["txt"])


# -------- SAFE JSON PARSER --------
def safe_json_load(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError("Invalid JSON from model")


# -------- GENERATE SLIDES --------
def generate_slides(transcript):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},  # 🔥 forces JSON
        messages=[
            {
                "role": "user",
                "content": f"""
Return ONLY valid JSON.

Format:
{{
  "slides": [
    {{
      "title": "Slide title",
      "points": ["point1", "point2"],
      "keywords": ["ai"]
    }}
  ]
}}

Rules:
- 5–8 slides
- Max 5 bullet points
- Short text
- No explanation outside JSON

Transcript:
{transcript}
"""
            }
        ]
    )

    return response.choices[0].message.content


# -------- SLIDES → SCRIPT --------
def slides_to_script(slides_json):
    data = safe_json_load(slides_json)
    slides = data["slides"]

    script = ""
    for slide in slides:
        script += slide["title"] + ". "
        script += " ".join(slide["points"]) + ". "

    return script


# -------- TEXT TO AUDIO --------
def text_to_audio(script):
    tts = gTTS(script)
    audio_file = "audio.mp3"
    tts.save(audio_file)
    return audio_file


# -------- FETCH BACKGROUND IMAGE --------
def get_image(keyword):
    url = f"https://source.unsplash.com/1280x720/?{keyword}"
    path = f"{keyword}.jpg"

    try:
        img_data = requests.get(url).content
        with open(path, "wb") as f:
            f.write(img_data)
        return path
    except:
        return None


# -------- CREATE VIDEO --------
def create_video(slides_json, audio_file):
    data = safe_json_load(slides_json)
    slides = data["slides"]

    audio = AudioFileClip(audio_file)
    duration = audio.duration
    slide_duration = duration / len(slides)

    clips = []

    for slide in slides:
        keyword = slide.get("keywords", ["technology"])[0]
        bg_img = get_image(keyword)

        # Background
        if bg_img:
            bg = ImageClip(bg_img).resize((1280, 720))
        else:
            bg = ColorClip(size=(1280, 720), color=(30, 30, 30))

        bg = bg.set_duration(slide_duration)

        # Dark overlay
        overlay = ColorClip(size=(1280, 720), color=(0, 0, 0)).set_opacity(0.5).set_duration(slide_duration)

        # Title
        title_clip = TextClip(
            slide["title"],
            fontsize=70,
            color="white",
            method="caption",
            size=(1000, None)
        ).set_position(("center", 80)).set_duration(slide_duration)

        # Bullets
        bullets = "\n\n".join([f"• {p}" for p in slide["points"]])

        bullet_clip = TextClip(
            bullets,
            fontsize=45,
            color="white",
            method="caption",
            size=(1000, None),
            align="West"
        ).set_position(("center", 250)).set_duration(slide_duration)

        slide_clip = CompositeVideoClip([bg, overlay, title_clip, bullet_clip])

        slide_clip = slide_clip.fadein(0.5).fadeout(0.5)

        clips.append(slide_clip)

    final_video = concatenate_videoclips(clips).set_audio(audio)

    output = "final_video.mp4"
    final_video.write_videofile(output, fps=24)

    return output


# -------- MAIN --------
if uploaded_file:
    transcript = uploaded_file.read().decode("utf-8")

    if st.button("Generate Video"):
        try:
            with st.spinner("Processing... ⏳"):
                slides_json = generate_slides(transcript)

                script = slides_to_script(slides_json)
                audio = text_to_audio(script)
                video = create_video(slides_json, audio)

            st.success("✅ Video Generated!")
            st.video(video)

        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
