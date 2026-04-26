import os
import json
import streamlit as st
from gtts import gTTS
from moviepy.editor import *
from openai import OpenAI
from PIL import Image
import requests

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.set_page_config(page_title="Pro Slide Video Generator")

st.title("🎬 AI Slide Video Generator (Pro)")
st.write("Generate presentation-style recap videos")

uploaded_file = st.file_uploader("Upload transcript (.txt)", type=["txt"])

# -------- Generate slides --------
def generate_slides(transcript):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": f"""
Convert transcript into presentation slides.

Format JSON:
[
  {{
    "title": "Slide title",
    "points": ["point1", "point2"],
    "keywords": ["ai", "data"] 
  }}
]

Rules:
- 5–8 slides
- Clean, short bullets
- Engaging titles
"""
        }]
    )
    return response.choices[0].message.content


# -------- Slides → narration --------
def slides_to_script(slides_json):
    slides = json.loads(slides_json)
    script = ""

    for slide in slides:
        script += slide["title"] + ". "
        script += " ".join(slide["points"]) + ". "

    return script


# -------- Voice --------
def text_to_audio(script):
    tts = gTTS(script)
    tts.save("audio.mp3")
    return "audio.mp3"


# -------- Get background image --------
def get_image(keyword):
    url = f"https://source.unsplash.com/1280x720/?{keyword}"
    img_path = f"{keyword}.jpg"

    try:
        img_data = requests.get(url).content
        with open(img_path, "wb") as f:
            f.write(img_data)
        return img_path
    except:
        return None


# -------- Create video --------
def create_video(slides_json, audio_file):
    slides = json.loads(slides_json)

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

        # Dark overlay (for readability)
        overlay = ColorClip(size=(1280,720), color=(0,0,0)).set_opacity(0.5).set_duration(slide_duration)

        # Title
        title_clip = TextClip(
            slide["title"],
            fontsize=70,
            color='white',
            method='caption',
            size=(1000, None)
        ).set_position(("center", 80)).set_duration(slide_duration)

        # Bullet points
        bullets = "\n\n".join([f"• {p}" for p in slide["points"]])

        bullet_clip = TextClip(
            bullets,
            fontsize=45,
            color='white',
            method='caption',
            size=(1000, None),
            align='West'
        ).set_position(("center", 250)).set_duration(slide_duration)

        slide_clip = CompositeVideoClip([bg, overlay, title_clip, bullet_clip])

        # Add fade effect
        slide_clip = slide_clip.fadein(0.5).fadeout(0.5)

        clips.append(slide_clip)

    final_video = concatenate_videoclips(clips).set_audio(audio)

    output = "final_video.mp4"
    final_video.write_videofile(output, fps=24)

    return output


# -------- MAIN --------
if uploaded_file:
    transcript = uploaded_file.read().decode("utf-8")

    if st.button("Generate Pro Video"):
        with st.spinner("Generating slides + video... ⏳"):
            slides_json = generate_slides(transcript)
            script = slides_to_script(slides_json)
            audio = text_to_audio(script)
            video = create_video(slides_json, audio)

        st.success("✅ Done!")
        st.video(video)