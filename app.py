import io
import os
import psycopg2
import pandas as pd
import streamlit as st
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from matplotlib import pyplot as plt
from openpyxl import Workbook
from dotenv import load_dotenv

# ---- Load environment variables ----
load_dotenv()
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_PORT = os.getenv("DB_PORT")

def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT,
        sslmode="require"
    )

# ---- Initialize database tables ----
def init_db():
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute('''
            CREATE TABLE IF NOT EXISTS boarders (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                room_no TEXT NOT NULL,
                username TEXT NOT NULL,
                pin TEXT NOT NULL,
                is_convenor INTEGER DEFAULT 0
            )
            ''')
            c.execute('''
            CREATE TABLE IF NOT EXISTS meals (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES boarders(id),
                meal_date TEXT,
                lunch INTEGER DEFAULT 0,
                dinner INTEGER DEFAULT 0,
                dinner_choice TEXT
            )
            ''')
            c.execute('''
            CREATE TABLE IF NOT EXISTS dinner_option (
                id SERIAL PRIMARY KEY,
                meal_date TEXT UNIQUE,
                option TEXT
            )
            ''')
            conn.commit()

init_db()

# ---------------------- UTILS ----------------------
def register_user(name, room, username, pin):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM boarders WHERE room_no=%s", (room,))
            if c.fetchone()[0] >= 2:
                st.error("This room already has 2 registered boarders.")
                return
            c.execute("SELECT * FROM boarders WHERE username=%s OR (name=%s AND room_no=%s)",
                      (username, name, room))
            if c.fetchone():
                st.warning("This boarder is already registered!")
            else:
                c.execute("INSERT INTO boarders (name, room_no, username, pin) VALUES (%s,%s,%s,%s)",
                          (name, room, username, pin))
                conn.commit()
                st.success("Registered successfully!")

def update_convenor_status(boarder_id, status):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE boarders SET is_convenor=%s WHERE id=%s", (status, boarder_id))
            conn.commit()

def get_all_boarders():
    with get_connection() as conn:
        query = "SELECT id, name, room_no, username, is_convenor FROM boarders"
        return pd.read_sql_query(query,conn)
    

def get_users_in_room(room):
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, name, pin FROM boarders WHERE room_no=%s", (room,))
            return c.fetchall()
        

def get_booking_date():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    if now.hour >= 20:
        return (now + timedelta(days=1)).date()
    elif now.hour < 1:
        return now.date()
    elif 6 <= now.hour < 16:
        return now.date()
    else:
        return None


def get_tomorrow_meals():
    meal_date = get_booking_date() or date.today()
    with get_connection() as conn:
        df = pd.read_sql_query("""
            SELECT b.name, b.room_no, m.lunch, m.dinner, m.dinner_choice
            FROM meals m
            JOIN boarders b ON b.id = m.user_id
            WHERE m.meal_date = %s
            ORDER BY b.room_no
        """, conn, params=(str(meal_date),))

    df["lunch"] = pd.to_numeric(df["lunch"], errors="coerce").fillna(0).astype(int)
    df["dinner"] = pd.to_numeric(df["dinner"], errors="coerce").fillna(0).astype(int)
    totals_df = pd.DataFrame({
        "name": ["TOTAL"], "room_no": [" "],
        "lunch": [df["lunch"].sum()],
        "dinner": [df["dinner"].sum()],
        "dinner_choice": [""]
    })
    return pd.concat([df, totals_df], ignore_index=True)

def total_grocery(df):
    return pd.DataFrame({
        "item": ["Egg", "Fish", "Chicken"],
        "dinner": [
            df[df["dinner_choice"] == "Egg"]["dinner"].sum(),
            df[df["dinner_choice"] == "Fish"]["dinner"].sum(),
            df[df["dinner_choice"] == "Chicken"]["dinner"].sum()
        ]
    })

def book_meal(user_id, lunch, dinner, dinner_choice):
    meal_date = get_booking_date()
    if meal_date is None:
        st.error("Booking not allowed at this time!")
        return
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("SELECT * FROM meals WHERE user_id=%s AND meal_date=%s", (user_id, str(meal_date)))
            if c.fetchone():
                c.execute("""UPDATE meals SET lunch=%s, dinner=%s, dinner_choice=%s
                             WHERE user_id=%s AND meal_date=%s""",
                          (lunch, dinner, dinner_choice, user_id, str(meal_date)))
            else:
                c.execute("""INSERT INTO meals (user_id, meal_date, lunch, dinner, dinner_choice)
                             VALUES (%s,%s,%s,%s,%s)""",
                          (user_id, str(meal_date), lunch, dinner, dinner_choice))
            conn.commit()
    st.success("Meal booked successfully!")

def validate_convenor(username, room, pin):
    if username == "sahid" and room == "47" and pin == "1202":
        return "superadmin"
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("SELECT is_convenor FROM boarders WHERE username=%s AND room_no=%s AND pin=%s",
                      (username, room, pin))
            row = c.fetchone()
            return row is not None and row[0] == 1

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Meals')
    return output.getvalue()

def set_dinner_option(option):
    meal_date = get_booking_date()
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute('''INSERT INTO dinner_option (meal_date, option)
                         VALUES (%s,%s)
                         ON CONFLICT (meal_date) DO UPDATE SET option = EXCLUDED.option''',
                      (str(meal_date), option))
            conn.commit()

def check_dinner_option():
    meal_date = get_booking_date()
    with get_connection() as conn:
        with conn.cursor() as c:
            c.execute("SELECT option FROM dinner_option WHERE meal_date=%s", str(meal_date,))
            row = c.fetchone()
            return row[0] if row else "Chicken"

# ---------------------- STREAMLIT UI ----------------------
st.title("Hostel Meal Booking System")
menu = st.sidebar.selectbox("Menu", ["Home", "Register", "Book Meal", "Admin Panel"])

#--------------------------HOME PAGE---------------------------
if menu == "Home":
    st.header("Old PG Boys' Hostel")
    st.subheader("Notice Board")
    st.info("Meal booking closes daily at 4 PM. Emergency meal booking is allowed only by convenors.")
    st.subheader("Current Convenors")
    convenors_df = get_all_boarders()
    convenors_df = convenors_df[convenors_df['is_convenor'] == 1]
    st.dataframe(convenors_df[['name', 'room_no']])

#---------------------------REGISTER------------------------------
elif menu == "Register":
    st.header("User Registration")
    name = st.text_input("Full Name")
    room = st.text_input("Room Number")
    username = st.text_input("Username")
    pin = st.text_input("Enter 4-digit PIN", type="password", max_chars=4)
    if st.button("Register") and (len(pin) == 4) and pin.isdigit():
        if name and room and username:
            register_user(name.strip(), room.strip(), username.strip(), pin.strip())
        else:
            st.warning("Please fill all fields")
    else:
        st.warning("Enter a 4-digit PIN!")

#--------------------------------Book Meal----------------------------------------
elif menu == "Book Meal":
    st.header("Meal Booking")
    meal_date = get_booking_date()
    if meal_date is None:
        st.error("Booking is closed right now. Come back at 8PM–1AM or 6AM–4PM.")
    else:
        st.success(f"You are booking for {meal_date}")
        room = st.text_input("Enter Your Room Number")
        if "users" not in st.session_state:
            st.session_state.users = []

        if st.button("Fetch Names"):
            st.session_state.users = get_users_in_room(room.strip())

        if st.session_state.users:
            selected_user = st.selectbox("Select Your Name", [u[1] for u in st.session_state.users])

            #-------------------options---------------------
            book_lunch = st.checkbox("Lunch", value=True)
            book_dinner = st.checkbox("Dinner", value=True)
            dinner_choice = st.radio("Dinner Choice", ["Egg", "Fish"] if check_dinner_option() == "Fish" else ["Egg", "Chicken"])

            pin = st.text_input("Enter 4-digit pin")
            if st.button("Book Meal"):
                user_id = [u[0] for u in st.session_state.users if u[1] == selected_user][0]
                if pin == [u[2] for u in st.session_state.users if u[1] == selected_user][0]:
                    book_meal(user_id, book_lunch, book_dinner, dinner_choice)
                else:
                    st.warning("Invalid PIN")
        else:
            st.error("No boarders registered to this room. Register first!")


#-----------------------------------ADMIN PANEL----------------------------------
elif menu == "Admin Panel":
    st.header("Admin Panel")

    if "admin_role" not in st.session_state:
        st.session_state.admin_role = None
    if st.session_state.admin_role is None:
        username = st.text_input("Admin Username")
        room = st.text_input("Room no.")
        pin = st.text_input("Admin Password", type="password")
        if st.button("Login"):
            role = validate_convenor(username, room, pin)
            if role == "superadmin":
                st.session_state.admin_role = "superadmin"
                st.success("Superadmin Access Granted!")
            elif role:
                st.session_state.admin_role = "convenor"
                st.success("Convenor Access Granted!")
            else:
                st.error("Invalid Username or Password")

#-----------------superadmin--------------------------
    if st.session_state.admin_role == "superadmin":
        st.subheader("Superadmin Panel")
        boarders_df = get_all_boarders()
        st.dataframe(boarders_df)
        selected_id = st.selectbox("Select Boarder ID to Change Convenor Status", boarders_df['id'].tolist())
        new_status = st.radio("Set as Convenor?", [0, 1])
        if st.button("Update Convenor Status"):
            update_convenor_status(selected_id, new_status)
            st.success("Convenor status updated successfully!")

#-----------------convenor----------------------------
    elif st.session_state.admin_role == "convenor":
        st.subheader("Convenor Panel")
        meal_date = get_booking_date() or date.today()
        df = get_tomorrow_meals()
        grocery_df = total_grocery(df)
        st.subheader("Meal Data")
        st.dataframe(df)
        st.subheader("Grocery Requirements")
        st.dataframe(grocery_df)

        #-------matplotlib-----------
        fig, ax = plt.subplots()
        ax.bar(grocery_df['item'], grocery_df['dinner'], color=['grey', 'skyblue', 'yellow'])
        ax.set_xlabel("Items")
        ax.set_ylabel("Count")
        ax.set_title("Dinner Item Distribution")
        st.pyplot(fig)

        #-----------excel-----------
        excel_data = to_excel(df)
        st.download_button("Download Meal List", excel_data, "tomorrow_meals.xlsx")

        #----------------Allowed option---------------
        allowed_option = st.selectbox("Select the non-Veg Option", ["Fish", "Chicken"])
        if st.button("Set Dinner Option"):
            set_dinner_option(allowed_option)
            st.success(f"Dinner option is successfully added for {meal_date} to Egg + {allowed_option}")