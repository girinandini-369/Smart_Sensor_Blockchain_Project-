import streamlit as st
import asyncio
import time
from web3 import Web3
from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware
from telegram import Bot
from collections import deque
import pandas as pd

# ---------------- Configuration ----------------
TOKEN = "7494163279:AAHIXZkCLLuaSeWMtLwRfH6dkzTiJ46l6RE"
CHAT_ID = 6435594534
bot = Bot(token=TOKEN)

GANACHE_RPC = "http://127.0.0.1:7545"
TARGET_ACCOUNT = "0x90BDC71919447D5319E41dD24C72DC3eaa39bdA2"
TARGET_PRIVATE_KEY = "0x2868c8227b1bf9642321490c96ff052b9eb673fe49c218a003312bf21de0abab"
AUTO_FUND_WEI = Web3.to_wei(1, "ether")  # 1 ETH if needed

GAS_THRESHOLD = 200
TEMP_THRESHOLD = 40
MAX_HISTORY = 50  # max readings to show in charts
# ------------------------------------------------

def normalize_privkey(pk: str) -> str:
    return pk[2:] if pk.startswith("0x") else pk

async def send_telegram_alert(message: str):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
    except Exception as e:
        st.error(f"Telegram send error: {e}")

# Connect to Ganache
w3 = Web3(Web3.HTTPProvider(GANACHE_RPC))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

st.set_page_config(page_title="Smart Sensor Dashboard", layout="wide")
st.title("🚨 Smart Sensor Alert System Dashboard (Simulation)")

if not w3.is_connected():
    st.error("❌ Cannot connect to Ganache RPC. Make sure Ganache GUI is running on port 7545.")
    st.stop()
st.success("✅ Connected to Ganache blockchain")

TARGET_PRIVATE_KEY = normalize_privkey(TARGET_PRIVATE_KEY)

# ------------------ State ------------------
if 'gas_history' not in st.session_state:
    st.session_state.gas_history = deque(maxlen=MAX_HISTORY)
if 'temp_history' not in st.session_state:
    st.session_state.temp_history = deque(maxlen=MAX_HISTORY)
if 'alert_state' not in st.session_state:
    st.session_state.alert_state = False
if 'alert_history' not in st.session_state:
    st.session_state.alert_history = []

# ------------------ Layout Tabs ------------------
tab1, tab2, tab3 = st.tabs(["Sensors", "Alerts History", "Blockchain Logs"])

with tab1:
    st.subheader("⚙️ Sensor Simulation")
    col1, col2, col3 = st.columns(3)
    with col1:
        gas_value = st.slider("Gas Level", 0, 500, 100)
    with col2:
        temp_value = st.slider("Temperature (°C)", 20, 50, 30)
    with col3:
        tilt_status = st.selectbox("Tilt Status", ["Stable", "Tilt Detected"])

    # Update history
    st.session_state.gas_history.append(gas_value)
    st.session_state.temp_history.append(temp_value)

    # Live charts
    st.line_chart(pd.DataFrame({"Gas": list(st.session_state.gas_history)}))
    st.line_chart(pd.DataFrame({"Temperature": list(st.session_state.temp_history)}))

    # Check alert
    alert_triggered = False
    alert_message = ""
    if gas_value > GAS_THRESHOLD:
        alert_triggered = True
        alert_message += f"🚨 Gas Leak Detected! Level: {gas_value}\n"
    if temp_value > TEMP_THRESHOLD:
        alert_triggered = True
        alert_message += f"🔥 High Temperature: {temp_value}°C\n"
    if tilt_status == "Tilt Detected":
        alert_triggered = True
        alert_message += "⚠️ Tilt Detected! Possible instability.\n"

    # Alert notification logic
    if alert_triggered and not st.session_state.alert_state:
        st.session_state.alert_state = True
        asyncio.run(send_telegram_alert(alert_message))
        st.success("⚠️ Alert triggered! Telegram notification sent.")
        st.session_state.alert_history.append({"Time": time.strftime("%H:%M:%S"), "Type": "Alert", "Message": alert_message})
    elif not alert_triggered and st.session_state.alert_state:
        # back to normal
        st.session_state.alert_state = False
        back_normal_msg = "✅ All safe now."
        asyncio.run(send_telegram_alert(back_normal_msg))
        st.success("Sensors normalized. Telegram notification sent.")
        st.session_state.alert_history.append({"Time": time.strftime("%H:%M:%S"), "Type": "Normal", "Message": back_normal_msg})
    else:
        st.info("✅ All sensors stable." if not alert_triggered else "⚠ Alert ongoing.")

with tab2:
    st.subheader("📋 Alerts History")
    if st.session_state.alert_history:
        st.table(pd.DataFrame(st.session_state.alert_history))
    else:
        st.info("No alerts yet.")

with tab3:
    st.subheader("📜 Blockchain Transactions")
    tx_lines = []
    for block_num in range(w3.eth.block_number + 1):
        block = w3.eth.get_block(block_num, full_transactions=True)
        for tx in block.transactions:
            tx_lines.append({
                "Block": block_num,
                "Tx Hash": tx.hash.hex(),
                "From": tx['from'],
                "To": tx['to'],
                "Value (ETH)": float(w3.from_wei(tx['value'], 'ether'))
            })
    if tx_lines:
        st.table(pd.DataFrame(tx_lines))
    else:
        st.info("No transactions yet.")
