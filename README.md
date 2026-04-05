# Jellyfish Outbreak API 🪼

FastAPI backend שמספק נתונים חיים מ-6 מקורות לדשבורד ניטור מדוזות.

## מקורות נתונים
- **iNaturalist** – תצפיות ביולוגיות עם GPS
- **YouTube** – סרטונים לפי אזור וחודש
- **MediaCloud** – כתבות עיתונות
- **Reddit** – פוסטים ציבוריים
- **Google Trends** – עניין חיפוש
- **Tumblr** – פוסטים ציבוריים

## Deploy ל-Render (חינמי)

### שלב 1 – GitHub
```bash
git init
git add .
git commit -m "initial"
# צור repo ב-github.com ואז:
git remote add origin https://github.com/YOUR_USER/jellyfish-api.git
git push -u origin main
```

### שלב 2 – Render
1. כנס ל-[render.com](https://render.com) והירשם
2. לחץ **New → Web Service**
3. חבר את ה-GitHub repo שיצרת
4. Render יזהה את `render.yaml` אוטומטית
5. תחת **Environment Variables** הוסף:
   - `YOUTUBE_API_KEY` = המפתח שלך
   - `MEDIACLOUD_API_KEY` = המפתח שלך
6. לחץ **Deploy**

### שלב 3 – עדכן את הדשבורד
אחרי ה-deploy תקבל URL בצורה:
```
https://jellyfish-api.onrender.com
```
עדכן את הדשבורד (Artifact) עם ה-URL הזה.

## הרצה מקומית
```bash
pip install -r requirements.txt
cp .env.example .env  # ערוך עם המפתחות שלך
uvicorn main:app --reload
```
API docs זמין ב: http://localhost:8000/docs

## Endpoints
| Endpoint | תיאור |
|----------|-------|
| `GET /api/inaturalist?region=mediterranean&year=2024` | תצפיות iNaturalist |
| `GET /api/youtube?region=mediterranean&year=2024` | סרטוני YouTube |
| `GET /api/mediacloud?region=mediterranean&year=2024` | כתבות עיתונות |
| `GET /api/reddit?region=mediterranean` | פוסטי Reddit |
| `GET /api/trends?region=mediterranean` | Google Trends |
| `GET /api/tumblr?region=mediterranean` | פוסטי Tumblr |
| `GET /api/combined?region=mediterranean&year=2024` | ציון משולב מכל המקורות |

## אזורים זמינים
`mediterranean`, `red_sea`, `black_sea`, `north_sea`, `atlantic`, `pacific`

## טקסונים זמינים
`scyphozoa`, `medusozoa`, `physalia`
