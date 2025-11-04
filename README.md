🚚 Water Truck Dispatch App

A lightweight Streamlit web app for managing and predicting water deliveries for a water truck company.

📋 Features

Customer Management

Add and update customers (name, address, phone, notes)

Automatically geocodes addresses for map display

Interactive Map

Visualize all customer locations with pop-up info

Embedded Folium map (no external dependencies needed)

Service Order View

Displays customers sorted by soonest due date

Highlights deliveries:

🟥 Red – Overdue

🟩 Green – Due today

🟧 Tan – Future deliveries

Includes Gallons Needed (median of past fills if recorded)

Downloadable CSV schedule

Fill Recording

Log each delivery and gallons delivered

Updates last fill date and predictive scheduling

🧠 Prediction Logic

Calculates the median interval between past fills per customer

Predicts next due date based on that interval

Orders customers by due date for efficient route planning

⚙️ Setup & Run
1. Install dependencies
pip install streamlit pandas sqlalchemy pydantic folium geopy numpy

2. Launch the app
streamlit run app.py

3. Usage

Add customers via the sidebar

Record fills (including gallons)

View and download your Service Order table

🗺️ Map Notes

Geocoding uses Nominatim (OpenStreetMap) — free but rate-limited.

For production, use Mapbox or Google Maps API for faster and more reliable geocoding.

🧾 Data Storage

Uses a simple SQLite database (watertruck.db) by default

Easy to migrate to PostgreSQL for production

🚀 Future Enhancements

Driver mobile interface for marking fills in real time

SMS/email reminders to customers before scheduled deliveries

Integration with Mapbox routing for optimal delivery paths
