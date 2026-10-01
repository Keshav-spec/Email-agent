# DeadlinePilot Deployment Guide: Render.com

This guide provides simple, step-by-step instructions to deploy your **DeadlinePilot Web Application** for free on [Render.com](https://render.com).

---

## Option 1: 1-Click Blueprint (Recommended)

Because we added [`render.yaml`](./render.yaml), Render can automatically configure the build command, start command, and environment variable schema for you.

1. **Sign in to Render**:
   - Go to [dashboard.render.com](https://dashboard.render.com/) (sign in with your GitHub account).
2. **Create New Blueprint**:
   - Click the **New +** button in the top right.
   - Select **Blueprint**.
3. **Connect Your Repository**:
   - Select `Keshav-spec/Email-agent`.
4. **Enter Your Environment Secrets**:
   Render will prompt you for the secrets marked in `render.yaml`:
   - `EMAIL_ADDRESS`: Your connected email (e.g., `keshav.sharma2023@vitstudent.ac.in`)
   - `EMAIL_PASSWORD`: Your 16-character Google App Password (e.g., `wzsb ugzl bayr zgci`)
   - `GEMINI_API_KEY`: Your Google Gemini API Key
5. **Click "Apply"**:
   - Render will build the environment and deploy your web app.
   - You will get a live public HTTPS URL (e.g., `https://deadline-pilot.onrender.com`).

---

## Option 2: Standard Web Service Setup

If you prefer setting it up manually without Blueprint:

1. Go to [dashboard.render.com](https://dashboard.render.com/) -> **New +** -> **Web Service**.
2. Connect your GitHub repository: `Keshav-spec/Email-agent`.
3. Configure the settings:
   - **Name**: `deadline-pilot` (or any name you like)
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn src.server:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: `Free`
4. Under **Environment Variables**, add:
   - `EMAIL_ADDRESS` = `your-email@domain.com`
   - `EMAIL_PASSWORD` = `your-app-password`
   - `GEMINI_API_KEY` = `your-gemini-api-key`
   - `GEMINI_MODEL` = `gemini-3-flash-preview`
   - `TODAY_ONLY` = `True`
   - `UNREAD_ONLY` = `False`
   - `ALERT_WINDOW_MINUTES` = `60`
5. Click **Create Web Service**.

---

## Automatic Continuous Deployment
Every time you push changes to the `main` branch of `https://github.com/Keshav-spec/Email-agent.git`, Render will automatically rebuild and deploy the new version.
