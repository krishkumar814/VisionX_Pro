import os

class Config:
    SECRET_KEY = "c68935b15223846f22c9397bbc329f969f9779c8fb8fb3e3"
    SQLALCHEMY_DATABASE_URI = 'sqlite:///visionx_v4.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'static/uploads'
    GEMINI_API_KEY = "AIzaSyAYGoiSvjb-V5Mc31Bybc0XrwIaS4PIu3M"