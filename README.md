# Driving Assistant API

FastAPI pozadinski sustav koji obrađuje OBD podatke o vožnjama, agregira statistike vozača i ostvaruje AI sučelje za personalizirane uvide u vožnju.

## Pozivi:
Obrada podataka (/process-trip/{trip_id}):
• Izračun udaljenosti, trajanja, brzine i drugih metrika za određenu vožnju.
• Spremanje metrika pojedinačnih vožnji u MongoDB, ažuriranje metrika po vozaču i globalnih prosjeka.

## Virtualni asistent (/ask):
• Klasifikacija korisničke namjere (npr. get_user_average, compare_user_to_all, get_current_trip).
• Dohvat podataka iz MongoDB-a prema potrebi i slanje upita Perplexity AI modelu za dobivanje odgovora.
• Podrška za izravnu analizu vožnje ili vozača putem dodatnih argumenata.

## Preduvjeti:
Python 3.9+
MongoDB Atlas (ili lokalni MongoDB) s kolekcijama: Drivers, Trips, OdbData, DriversReviewTrip, TripSummary, DriverSummary, AverageDriverData
API ključ za Perplexity AI

## Instalacija:
```bash
git clone https://github.com/lf53321/diplomski.git

pip install fastapi uvicorn pymongo pandas geopy python-dotenv requests
```

Potrebno je kreirati .env datoteku u korijenu repozitorija i unijeti vrijednosti:
```bash
MONGO_URI=<MongoDB URI>
API_KEY=<Perplexity API ključ>
```

