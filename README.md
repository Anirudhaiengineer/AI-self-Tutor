# AI Self Tutor

AI Self Tutor is a full-stack learning assistant with:

- FastAPI backend
- MongoDB user auth and schedule storage
- React + Vite frontend
- Live system-audio transcription with Whisper
- Transcript summary notes and chat
- Knowledge-test-driven schedule generation
- Short-term and long-term learning plans
- Study monitoring based on transcript-topic matching

## Requirements

- Python 3.11+ installed on your system
- Node.js 18+ and npm
- MongoDB running locally or a MongoDB Atlas connection string
- A Hugging Face token for the model-based features

## Setup

### 1) Clone the repo

```bash
git clone https://github.com/Anirudhaiengineer/AI-self-Tutor.git
cd AI-self-Tutor
```

### 2) Backend setup

Create the backend virtual environment and install dependencies:

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in `backend/` using `backend/.env.example` as the template.

Example values:

```env
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=project1
SECRET_KEY=change-this-secret-key
TOKEN_EXPIRE_SECONDS=3600
AUDIO_SAMPLE_RATE=44100
AUDIO_CHUNK_SECONDS=5
STT_MODE=whisper
STT_LANGUAGE=en
WHISPER_MODEL=tiny
HF_BASE_URL=https://router.huggingface.co/v1
HF_CHAT_MODEL=openai/gpt-oss-20b
HF_TOKEN=your_huggingface_token_here
```

Run the backend:

```bash
uvicorn app.main:app --reload
```

The backend runs on `http://127.0.0.1:8000` by default.

### 3) Frontend setup

Install dependencies and start the frontend:

```bash
cd ../frontend
npm install
npm run dev
```

If you want to point the frontend to a different backend URL, create `frontend/.env` from `frontend/.env.example` and set:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## How to use

1. Open the frontend URL shown by Vite.
2. Register or log in.
3. You will land on the dashboard first.
4. Use **Create Schedule** to open the planner.
5. Enter the learning goal.
6. Complete the knowledge test.
7. Accept the generated schedule.
8. Use the recorder dashboard to monitor transcription, summary notes, and study progress.

## Project structure

- `backend/` - FastAPI API, MongoDB access, transcription, diagnostics, and learning plans
- `frontend/` - React UI for auth, dashboard, planning, recorder, and chat

## Notes

- `backend/.env` and `frontend/.env` are intentionally ignored by git.
- The project depends on MongoDB for persistence.
- Whisper-based transcription may take a moment the first time it loads a model.
