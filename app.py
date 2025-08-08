import io
import os
import psycopg2
from psycopg2 import pool
import pandas as pd
import streamlit as st
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from matplotlib import pyplot as plt
from openpyxl import Workbook
import random
from dotenv import load_dotenv
import base64

# ---- Custom Sidebar Background Image ----
# A function to encode your image to a Base64 string
def get_base64_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode()

#------------------------------------------------------------------------------------------
# Replace 'path/to/your/image.jpg' with the actual path to your image file
#image_path = "assets/Creeper2.jpeg"
#image_base64 = get_base64_image(image_path)

# Inject custom CSS for the sidebar
#st.markdown(
#    f"""
#    <style>
#    [data-testid="stSidebar"] {{
#        background-image: url("data:image/jpeg;base64,{image_base64}");
#        background-size: cover;
#        background-position: center;
#        background-repeat: no-repeat;
#    }}
#    </style>
#    """,
#    unsafe_allow_html=True,
#)
import streamlit as st
from streamlit import config

st.markdown("""
<style>
.stAppHeader {
  background-color: transparent !important;
}
</style>
""", unsafe_allow_html=True)

# ---- NEW: Make Streamlit Alerts Opaque ----
st.markdown("""
<style>
 /* Apply to all alert boxes */
.stAlert {
    border-radius: 12px !important;  /* Rounded corners */
    border: 1px solid black !important;  /* Thin black outline */
}
</style>
""", unsafe_allow_html=True)


st.markdown("""
    <style>
    /* INFO alert - blue */
        .st-at {
            background-color: rgba(95, 169, 237, 0.72) !important;
            border: 1px solid #004085;
            color: white;
        }

        /* SUCCESS alert - green */
        .st-fl {
            background-color: rgba(40, 194, 29, 0) !important;
            border: 1px solid #155724;
            color: white;
        }
        /* SUCCESS alert - green */
        .st-en {
            background-color: rgba(40, 194, 29, 0.72) !important;
            border: 1px solid #155724;
            color: white;
        }

        /* WARNING alert - yellow */
        .st-el {
            background-color: rgba(255, 193, 7, 0.68) !important;
            border: 1px solid #856404;
            color: white;
        }

        /* ERROR alert - red */
        .st-dx {
            background-color: rgba(220, 53, 69, 0.72) !important;
            border: 1px solid #721c24;
            color: white;;
        }
    </style>
""", unsafe_allow_html=True)


#-------------------------------------------------------------------------------------
def pick_random_image(folder="assets"):
    images = [os.path.join(folder, img) for img in os.listdir(folder)
             if img.lower().endswith((".png", ".jpg"))]
    return random.choice(images) if images else None

# Pick only once per session
if "bg_image" not in st.session_state:
    chosen_image = pick_random_image("assets")
    if chosen_image:
      st.session_state.bg_image = get_base64_image(chosen_image)

# Apply style
if "bg_image" in st.session_state:
     st.markdown(f"""
        <style>
         .stApp {{
            background-image: url("data:image/jpeg;base64,{st.session_state.bg_image}");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
        }}
        </style>
    """, unsafe_allow_html=True)
#---------------------------------------------------------------------------------



#------------------------TEXT OUTLINE-----------------------------------
st.markdown("""
<style>
[data-testid="stAppViewContainer"] *:not(.stAlert):not(.stAlert *):not(.stNotification):not(.stNotification *) {
    color: inherit;
    -webkit-text-stroke: 0.5px black;
    paint-order: stroke fill;
    text-shadow:
        -0.5px -0.5px 0 black,
         0.5px -0.5px 0 black,
        -0.5px  0.5px 0 black,
         0.5px  0.5px 0 black;
}
</style>
""", unsafe_allow_html=True)
#------------------------------------------------------------------------



# ---- Load environment variables ----
# Best practice to have a .env file for local development
load_dotenv()
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_PORT = os.getenv("DB_PORT")
SUPERADMIN_USER = os.getenv("SUPERADMIN_USER")
SUPERADMIN_ROOM = os.getenv("SUPERADMIN_ROOM")
SUPERADMIN_PIN= os.getenv("SUPERADMIN_PIN")


# ---- Database Connection Pool ----
@st.cache_resource
def get_pool():
    """Initializes and returns a thread-safe connection pool."""
    try:
        # This pool is created once and cached for the entire app session.
        return psycopg2.pool.SimpleConnectionPool(
            1, 10, # minconn, maxconn
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            port=DB_PORT,
            sslmode="require"
        )
    except psycopg2.OperationalError as e:
        st.error(f"Fatal Error: Could not connect to the database. Please check credentials. Details: {e}")
        st.stop() # Halts the app if DB connection fails

pool = get_pool()

# Ensure the pool is closed when Streamlit shuts down the app
import atexit
@atexit.register
def close_pool():
    if pool:
        pool.closeall()

# ---- Database Wrapper Functions ----
# These wrappers are the core of the fix. They ensure every connection
# is ALWAYS returned to the pool, preventing leaks.

def execute_query(query, params=None, fetch=None):
    """
    Executes a query using a connection from the pool.
    `fetch` can be 'one', 'all', or None (for COMMIT operations).
    This function guarantees the connection is released.
    """
    conn = None
    try:
        conn = pool.getconn()
        with conn.cursor() as c:
            c.execute(query, params)
            if fetch == 'one':
                return c.fetchone()
            elif fetch == 'all':
                return c.fetchall()
            conn.commit() # Commit changes for INSERT, UPDATE, DELETE
            return c.rowcount
    except Exception as e:
        st.error(f"Database Error: {e}")
        if conn:
            conn.rollback() # Roll back transaction on error
        return None # Indicate failure
    finally:
        if conn:
            pool.putconn(conn) # This block ALWAYS runs, ensuring connection is returned.

def query_to_dataframe(query, params=None):
    """
    Executes a query and returns the result as a Pandas DataFrame.
    Guarantees the connection is released.
    """
    conn = None
    try:
        conn = pool.getconn()
        df = pd.read_sql_query(query, conn, params=params)
        return df
    except Exception as e:
        st.error(f"Database Error: {e}")
        return pd.DataFrame() # Return empty DataFrame on error
    finally:
        if conn:
            pool.putconn(conn)


# ---- Initialize database tables ----
@st.cache_resource
def initialize_tables():
    """Creates all necessary tables if they don't exist using the safe wrapper."""
    execute_query('''
        CREATE TABLE IF NOT EXISTS boarders (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            room_no TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            pin TEXT NOT NULL,
            is_convenor INTEGER DEFAULT 0
        )
    ''')
    execute_query('''
        CREATE TABLE IF NOT EXISTS meals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES boarders(id) ON DELETE CASCADE,
            meal_date DATE NOT NULL,
            lunch INTEGER DEFAULT 0,
            dinner INTEGER DEFAULT 0,
            dinner_choice TEXT,
            UNIQUE(user_id, meal_date) -- Prevents duplicate bookings for the same user on the same day
        )
    ''')
    execute_query('''
        CREATE TABLE IF NOT EXISTS dinner_option (
            id SERIAL PRIMARY KEY,
            meal_date DATE UNIQUE NOT NULL,
            option TEXT
        )
    ''')
    execute_query('''
        CREATE TABLE IF NOT EXISTS notices (
            id SERIAL PRIMARY KEY,
            notice_date DATE DEFAULT CURRENT_DATE,
            notice TEXT NOT NULL,
            posted_by TEXT NOT NULL REFERENCES boarders(username) ON DELETE CASCADE
        )
    ''')

# Call only once at the start of the app
initialize_tables()

# ---------------------- UTILS ----------------------
def register_user(name, room, username, pin):
    """Registers a new user after validation."""
    count_result = execute_query("SELECT COUNT(*) FROM boarders WHERE room_no=%s", (room,), fetch='one')
    if count_result and count_result[0] >= 2:
        st.error("This room already has 2 registered boarders.")
        return

    existing_user = execute_query("SELECT * FROM boarders WHERE username=%s", (username,), fetch='one')
    if existing_user:
        st.warning("This username is already taken. Please choose another one.")
    else:
        execute_query(
            "INSERT INTO boarders (name, room_no, username, pin) VALUES (%s,%s,%s,%s)",
            (name, room, username, pin)
        )
        st.success("Registered successfully! You can now book your meals.")

def update_convenor_status(boarder_id, status):
    """Updates the convenor status for a given boarder."""
    execute_query("UPDATE boarders SET is_convenor=%s WHERE id=%s", (status, boarder_id))

def get_all_boarders():
    """Returns a DataFrame of all boarders."""
    return query_to_dataframe("SELECT id, name, room_no, username, is_convenor FROM boarders ORDER BY room_no, name")

def get_users_in_room(room):
    """Fetches all users in a specific room."""
    return execute_query("SELECT id, name, pin FROM boarders WHERE room_no=%s", (room,), fetch='all')

def get_booking_date():
    """
    Determines the correct date for meal booking based on the current time in IST.
    Booking Windows: 8 PM - 1 AM (for next day) and 6 AM - 4 PM (for current day).
    """
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    if now.hour >= 20:  # 8 PM onwards -> Booking for tomorrow
        return (now + timedelta(days=1)).date()
    elif now.hour < 1:  # Midnight to 1 AM -> Booking for today
        return now.date()
    elif 6 <= now.hour < 16:  # 6 AM to 4 PM -> Booking for today
        return now.date()
    else:  # Booking is closed
        return None

def get_meals_for_date(meal_date):
    """Fetches meal data for a specific date and calculates totals."""
    df = query_to_dataframe("""
        SELECT b.name, b.room_no, m.lunch, m.dinner, m.dinner_choice
        FROM meals m
        JOIN boarders b ON b.id = m.user_id
        WHERE m.meal_date = %s
        ORDER BY b.room_no, b.name
    """, params=(meal_date,))

    if df.empty:
        return df

    df["lunch"] = pd.to_numeric(df["lunch"], errors="coerce").fillna(0).astype(int)
    df["dinner"] = pd.to_numeric(df["dinner"], errors="coerce").fillna(0).astype(int)
    
    totals_df = pd.DataFrame({
        "name": ["TOTAL"], "room_no": [""],
        "lunch": [df["lunch"].sum()],
        "dinner": [df["dinner"].sum()],
        "dinner_choice": [""]
    })
    return pd.concat([df, totals_df], ignore_index=True)

def total_grocery(df):
    """Calculates grocery requirements from a meal DataFrame."""
    if df.empty or "dinner_choice" not in df.columns:
        return pd.DataFrame({"item": ["Egg", "Fish", "Chicken"], "dinner": [0, 0, 0]})
        
    return pd.DataFrame({
        "item": ["Egg", "Fish", "Chicken"],
        "dinner": [
            df[df["dinner_choice"] == "Egg"]["dinner"].sum(),
            df[df["dinner_choice"] == "Fish"]["dinner"].sum(),
            df[df["dinner_choice"] == "Chicken"]["dinner"].sum()
        ]
    })

def book_meal(user_id, lunch, dinner, dinner_choice, meal_date):
    """Books a meal using an atomic UPSERT, preventing race conditions."""
    lunch_val = 1 if lunch else 0
    dinner_val = 1 if dinner else 0

    query = """
        INSERT INTO meals (user_id, meal_date, lunch, dinner, dinner_choice)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id, meal_date) DO UPDATE SET
            lunch = EXCLUDED.lunch,
            dinner = EXCLUDED.dinner,
            dinner_choice = EXCLUDED.dinner_choice
    """
    execute_query(query, (user_id, meal_date, lunch_val, dinner_val, dinner_choice))
    st.success("Meal booked successfully!")

def validate_convenor(username, room, pin):
    """Validates convenor credentials, including a hardcoded superadmin."""
    if username == SUPERADMIN_USER and room == SUPERADMIN_ROOM and pin == SUPERADMIN_PIN:
        return "superadmin"
    
    row = execute_query(
        "SELECT is_convenor FROM boarders WHERE username=%s AND room_no=%s AND pin=%s",
        (username, room, pin),
        fetch='one'
    )
    if row and row[0] == 1:
        return "convenor"
    return None

def to_excel(df):
    """Converts a DataFrame to an in-memory Excel file."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Meals')
    return output.getvalue()

def set_dinner_option(option, meal_date):
    """Sets the non-veg dinner option for a given date."""
    query = '''
        INSERT INTO dinner_option (meal_date, option)
        VALUES (%s, %s)
        ON CONFLICT (meal_date) DO UPDATE SET option = EXCLUDED.option
    '''
    execute_query(query, (meal_date, option))

def get_dinner_option(meal_date):
    """Gets the non-veg dinner option, defaulting to 'Chicken'."""
    if not meal_date:
        return "Chicken"
    row = execute_query("SELECT option FROM dinner_option WHERE meal_date=%s", (str(meal_date),), fetch='one')
    return row[0] if row else "Chicken"

def post_notice(message, username):
    """Posts a new notice to the notice board."""
    if message == "" or not username:
        st.warning("Notice cannot be empty.")
        return
    execute_query("INSERT INTO notices (notice, posted_by) VALUES (%s, %s)", (message, username))
    st.success("Notice has been posted successfully!")

def get_notices():
    """Retrieves the 5 most recent notices from the last day."""
    query = """
        SELECT n.notice, b.name, n.notice_date
        FROM notices n
        JOIN boarders b ON n.posted_by = b.username
        WHERE n.notice_date >= CURRENT_DATE - INTERVAL '1 day'
        ORDER BY n.notice_date DESC, n.id DESC
        LIMIT 5;
    """
    return execute_query(query, fetch='all') or []



# ---------------------- STREAMLIT UI ----------------------
st.set_page_config(page_title="Hostel Meal System", layout="wide")
st.title("Hostel Meal Booking System")

menu = st.sidebar.selectbox("Menu", ["Home", "Register", "Book Meal", "Admin Panel","Reset PIN"])

#--------------------------HOME PAGE---------------------------
if menu == "Home":
    st.header("Old PG Boys' Hostel")
    
    st.subheader("Notice Board")
    notices = get_notices()

    with st.container():
        if notices:
            for text, author, n_date in notices:
                st.info(f'"{text}"')
                st.caption(f"— {author} on {n_date.strftime('%B %d, %Y')}")
        else:
            st.info("No recent notices.")



    st.divider()
    st.info("Meal booking is open from **6:00 AM to 4:00 PM** for the current day, and **8:00 PM to 1:00 AM** for the next day.")

    st.subheader("Current Convenors")
    convenors_df = get_all_boarders()
    convenors_df = convenors_df[convenors_df['is_convenor'] == 1]
    if not convenors_df.empty:
        st.dataframe(convenors_df[['name', 'room_no']], use_container_width=True)
    else:
        st.write("No convenors are currently assigned.")

#---------------------------REGISTER------------------------------
elif menu == "Register":
    st.header("User Registration")
    # Using st.form to prevent re-runs on every input change
    with st.form("registration_form"):
        name = st.text_input("Full Name")
        room = st.text_input("Room Number")
        username = st.text_input("Username (must be unique)")
        pin = st.text_input("Enter 4-digit PIN", type="password", max_chars=4)
        
        submitted = st.form_submit_button("Register")
        if submitted:
            if not all([name, room, username, pin]):
                st.warning("Please fill all fields.")
            elif len(pin) != 4 or not pin.isdigit():
                st.warning("PIN must be exactly 4 digits.")
            else:
                register_user(name.strip(), room.strip(), username.strip(), pin.strip())

#--------------------------------Book Meal----------------------------------------
elif menu == "Book Meal":
    st.header("Meal Booking")
    meal_date = get_booking_date()
    
    if meal_date is None:
        st.error("Booking is currently closed. Please check the timings on the Home page.")
    else:
        st.success(f"You are booking for: {meal_date.strftime('%A, %B %d, %Y')}")
        
        room = st.text_input("Enter Your Room Number")

        if room:
            users_in_room = get_users_in_room(room.strip())
            if users_in_room:
                user_map = {u[1]: (u[0], u[2]) for u in users_in_room} # Map name to (id, pin)
                selected_user_name = st.selectbox("Select Your Name", user_map.keys())
                
                if selected_user_name:
                    
                    # --- MOVE THESE WIDGETS OUTSIDE THE FORM ---
                    book_lunch = st.checkbox("Lunch", value=False)
                    book_dinner = st.checkbox("Dinner", value=False)
                    dinner_choice = None
                    
                    if book_dinner:
                        dinner_option_for_day = get_dinner_option(meal_date)
                        options = ["Egg", "Fish"] if dinner_option_for_day == "Fish" else ["Egg", "Chicken"]
                        dinner_choice = st.radio("Dinner Choice", options)
                    
                    # --- THE FORM STARTS HERE ---
                    with st.form("booking_form"):
                        entered_pin = st.text_input("Enter your 4-digit PIN to confirm", type="password", max_chars=4)
                        
                        book_button = st.form_submit_button("Book Meal")
                        
                        if book_button:
                            user_id, correct_pin = user_map[selected_user_name]
                            if entered_pin == correct_pin:
                                book_meal(user_id, book_lunch, book_dinner, dinner_choice, meal_date)
                            else:
                                st.error("Invalid PIN. Please try again.")
            elif room.strip():
                st.error("No boarders found for this room. Please register first or check the room number.")

#-----------------------------------ADMIN PANEL----------------------------------
elif menu == "Admin Panel":
    st.header("Admin Panel")

    # FIX: Initialize session state keys for admin role and username
    if "admin_role" not in st.session_state:
        st.session_state.admin_role = None
    if "admin_username" not in st.session_state:
        st.session_state.admin_username = None

    if st.session_state.admin_role is None:
        with st.form("admin_login"):
            username = st.text_input("Admin Username")
            room = st.text_input("Room No.")
            pin = st.text_input("Admin Password", type="password")
            
            login_button = st.form_submit_button("Login")
            if login_button:
                role = validate_convenor(username, room, pin)
                if role:
                    # FIX: Store both role and username in session state
                    st.session_state.admin_role = role
                    st.session_state.admin_username = username
                    st.success(f"{role.capitalize()} Access Granted!")
                    st.rerun()
                else:
                    st.error("Invalid Credentials or Not a Convenor.")
    else:
        st.sidebar.success(f"Logged in as: {st.session_state.admin_username} ({st.session_state.admin_role})")
        if st.sidebar.button("Logout"):
            st.session_state.admin_role = None
            st.session_state.admin_username = None
            st.rerun()

    # Superadmin can do everything a convenor can, plus manage convenors.
    if st.session_state.admin_role == "superadmin":
        st.subheader("Superadmin Panel: Manage Convenors")
        boarders_df = get_all_boarders()
        if not boarders_df.empty:
            st.dataframe(boarders_df, use_container_width=True)
            
            # UI for updating convenor status
            with st.expander("Update Convenor Status"):
                selected_id = st.selectbox("Select Boarder by ID", boarders_df['id'], format_func=lambda x: f"{x} - {boarders_df.loc[boarders_df['id'] == x, 'name'].iloc[0]}")
                current_status = boarders_df[boarders_df['id'] == selected_id]['is_convenor'].iloc[0]
                
                new_status = st.radio("Set as Convenor?", [1, 0], format_func=lambda x: "Yes" if x == 1 else "No", index=1 if current_status == 0 else 0)

                if st.button("Update Status"):
                    update_convenor_status(selected_id, new_status)
                    st.success("Convenor status updated successfully!")
                    st.rerun()
        else:
            st.info("No boarders found in the database.")

    if st.session_state.admin_role == "convenor":
        st.subheader("Convenor Panel")
        
        view_date = get_booking_date() or (datetime.now(ZoneInfo("Asia/Kolkata"))).date()
        st.info(f"Displaying meal data for: {view_date.strftime('%A, %B %d, %Y')}")

        df = get_meals_for_date(view_date)
        grocery_df = total_grocery(df)
        
        tab1, tab2, tab3 = st.tabs(["Meal List", "Grocery Chart", "Admin Actions"])

        with tab1:
            st.subheader("Meal Data")
            st.dataframe(df, use_container_width=True)
            excel_data = to_excel(df)
            st.download_button("Download as Excel", excel_data, f"meals_{view_date}.xlsx")

        with tab2:
            st.subheader("Grocery Requirements")
            st.dataframe(grocery_df, use_container_width=True)
            
            fig, ax = plt.subplots()
            ax.bar(grocery_df['item'], grocery_df['dinner'], color=['#ff9999','#66b3ff','#99ff99'])
            ax.set_ylabel("Count")
            ax.set_title("Dinner Item Distribution")
            st.pyplot(fig)

        with tab3:
            st.subheader("Set Dinner Option")
            date_for_option = get_booking_date()
            if date_for_option:
                allowed_option = st.selectbox("Select non-veg option for next booking", ["Chicken", "Fish"])
                if st.button("Set Dinner Option"):
                    set_dinner_option(allowed_option, date_for_option)
                    st.success(f"Dinner option for {date_for_option} set to Egg + {allowed_option}")
            else:
                st.warning("Dinner options can only be set during active booking hours.")

            st.subheader("Post Notice")
            with st.form("notice_form"):
                message = st.text_area("Enter Notice", placeholder="Example: Mess will be closed on Sunday.", height=100)
                post_button = st.form_submit_button("Post Notice")
                if post_button and message:
                    # FIX: Use the username stored in session state
                    post_notice(message, st.session_state.admin_username)


#-----------------------Forgot PIN--------------------------
elif menu == "Reset PIN":
    st.header("Reset Your PIN")
    with st.form("Reset the PIN"):
        username = st.text_input("Username")
        room = st.text_input("Room no.")
        new_pin = st.text_input("Enter Your New PIN",type="password",max_chars=4)
        reset_button = st.form_submit_button("Reset PIN")

        if reset_button:
            if len(new_pin) != 4 or not new_pin.isdigit():
                st.warning("PIN must be exactly 4 digits.")

            else:
                if not username or not room or not new_pin:
                    st.warning("Please fill out all the required fields!")
                
                query = """
                    UPDATE boarders
                    SET pin=%s
                    WHERE username=%s AND room_no=%s
                """
                rows = execute_query(query,(new_pin,username,room)) #Incase of UPDATE-PostgreSQL executes the query and internally counts how many rows were affected.
                if rows == 0:
                    st.session_state.reset_result = ("error","No matching boarder found!")
                else:
                    st.session_state.reset_result = ("success","PIN Updated Successfully!")
                st.rerun()
        #------After Rerun------
        if "reset_result" in st.session_state:
            info_type,info_text = st.session_state.reset_result

            if info_type == "error":
                st.error(info_text)
            else:
                st.success(info_text)
            del st.session_state.reset_result
                
