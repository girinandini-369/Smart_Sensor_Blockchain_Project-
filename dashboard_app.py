import streamlit as st
import asyncio
import time
from web3 import Web3
from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware
from telegram import Bot
from collections import deque
import pandas as pd
import plotly.express as px

# ---------------- Configuration (using account 0 from your list) ----------------
TOKEN = "7494163279:AAHIXZkCLLuaSeWMtLwRfH6dkzTiJ46l6RE"
CHAT_ID = 6435594534
bot = Bot(token=TOKEN)

GANACHE_RPC = "http://127.0.0.1:7545"

# Use account (0) — plenty of ETH on Ganache
TARGET_ACCOUNT = "0xdd2b8771ab3F3CA570C7ef21E8A7Fa0dd2e530B4"
TARGET_PRIVATE_KEY = "0x88b8c2690452b87160f26b4dcbd348d6ba5d54e75c38c2e70b35620e35462243"

GAS_THRESHOLD = 200
TEMP_THRESHOLD = 40
MAX_HISTORY = 50
# ------------------------------------------------

def normalize_privkey(pk: str) -> str:
    return pk[2:] if pk.startswith("0x") else pk

async def send_telegram_alert(message: str):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
    except Exception as e:
        # don't crash UI for telegram errors
        st.error(f"Telegram send error: {e}")

# Connect to Ganache
w3 = Web3(Web3.HTTPProvider(GANACHE_RPC))
# Ganache doesn't require POA middleware usually, but injecting a safe middleware doesn't hurt for testnets:
try:
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
except Exception:
    pass  # if middleware import fails or not needed, continue

st.set_page_config(page_title="Smart Sensor Dashboard", layout="wide")
st.title("🚨 Smart Sensor Alert System Dashboard (Simulation)")

if not w3.is_connected():
    st.error("❌ Cannot connect to Ganache RPC. Make sure Ganache GUI is running on port 7545.")
    st.stop()
st.success("✅ Connected to Ganache blockchain")

# normalize private key for web3 signing
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
if 'tx_history' not in st.session_state:
    st.session_state.tx_history = []

# ------------------ Utils: blockchain tx ------------------
def send_blockchain_tx_minimal():
    """
    Send a minimal, zero-value self-transfer transaction from TARGET_ACCOUNT to itself.
    This creates a transaction record that Ganache UI will show as mined.
    """
    try:
        # check balance
        balance = w3.eth.get_balance(TARGET_ACCOUNT)
        # minimal gas cost estimate (21000 gas * gasPrice)
        gas_price = w3.to_wei(1, 'gwei')
        min_gas_cost = 21000 * gas_price

        if balance < min_gas_cost:
            st.warning(f"⚠ Insufficient ETH to send TX. Account balance: {w3.from_wei(balance, 'ether')} ETH | Minimum required gas: {w3.from_wei(min_gas_cost, 'ether')} ETH")
            return None

        nonce = w3.eth.get_transaction_count(TARGET_ACCOUNT)
        tx = {
            "nonce": nonce,
            "to": TARGET_ACCOUNT,
            "value": 0,
            "gas": 21000,
            "gasPrice": gas_price,
            "chainId": w3.eth.chain_id,
        }

        signed = w3.eth.account.sign_transaction(tx, TARGET_PRIVATE_KEY)
        # use the correct attribute name: raw_transaction
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        # append to dashboard history
        st.session_state.tx_history.append({
            "Block": receipt.blockNumber,
            "Tx Hash": tx_hash.hex(),
            "From": TARGET_ACCOUNT,
            "To": TARGET_ACCOUNT,
            "Value (ETH)": 0.0,
            "Time": time.strftime("%Y-%m-%d %H:%M:%S")
        })

        st.success(f"✅ Blockchain TX successful: {tx_hash.hex()}")
        return tx_hash.hex()
    except Exception as e:
        st.error(f"Blockchain TX error: {e}")
        return None

# ------------------ Tabs / UI ------------------
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

    # show account info
    c1, c2 = st.columns([2, 3])
    with c1:
        st.info(f"**Using account:**\n`{TARGET_ACCOUNT}`")
    with c2:
        balance = w3.eth.get_balance(TARGET_ACCOUNT)
        st.success(f"**Balance:** {w3.from_wei(balance, 'ether')} ETH")

    # Update history
    st.session_state.gas_history.append(gas_value)
    st.session_state.temp_history.append(temp_value)

    # Plotly charts
    gas_df = pd.DataFrame({"Gas Level": list(st.session_state.gas_history)})
    temp_df = pd.DataFrame({"Temperature": list(st.session_state.temp_history)})
    gas_fig = px.line(gas_df, y="Gas Level", title="Gas Levels Over Time")
    temp_fig = px.line(temp_df, y="Temperature", title="Temperature Over Time")
    st.plotly_chart(gas_fig, use_container_width=True)
    st.plotly_chart(temp_fig, use_container_width=True)

    # ------------------ Alert logic ------------------
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

    if alert_triggered:
        st.warning("⚠ Alert Active!")
    else:
        st.success("✅ All sensors normal and stable.")

    # Trigger actions only on state change
    if alert_triggered and not st.session_state.alert_state:
        st.session_state.alert_state = True
        # send telegram
        try:
            asyncio.run(send_telegram_alert(alert_message))
            st.info("✅ Telegram alert sent.")
        except Exception:
            st.warning("Telegram send attempt failed (but dashboard continues).")
        # send a minimal blockchain TX to log the alert
        send_blockchain_tx_minimal()
        st.session_state.alert_history.append({"Time": time.strftime("%Y-%m-%d %H:%M:%S"), "Type": "Alert", "Message": alert_message})
    elif not alert_triggered and st.session_state.alert_state:
        st.session_state.alert_state = False
        back_msg = "✅ All sensors back to normal."
        try:
            asyncio.run(send_telegram_alert(back_msg))
            st.info("✅ Telegram normalization message sent.")
        except Exception:
            st.warning("Telegram send attempt failed.")
        send_blockchain_tx_minimal()
        st.session_state.alert_history.append({"Time": time.strftime("%Y-%m-%d %H:%M:%S"), "Type": "Normal", "Message": back_msg})

with tab2:
    st.subheader("📋 Alerts History")
    if st.session_state.alert_history:
        df_history = pd.DataFrame(st.session_state.alert_history)
        # highlight alerts
        def highlight_alert(row):
            return ['background-color: red; color: white' if row['Type'] == 'Alert' else '' for _ in row]
        st.dataframe(df_history.style.apply(highlight_alert, axis=1), use_container_width=True)
    else:
        st.info("No alerts yet.")

with tab3:
    st.subheader("📜 Blockchain Transactions (local Ganache)")
    if st.session_state.tx_history:
        df_tx = pd.DataFrame(st.session_state.tx_history)
        st.dataframe(df_tx.sort_values(by="Block", ascending=False), use_container_width=True)
    else:
        st.info("No transactions yet. (Trigger an alert to create a short self-transfer TX that will appear in Ganache.)")

# footer tip
st.markdown("---")
st.caption("Tip: If Ganache UI doesn't show transactions, open Ganache GUI -> click the workspace -> switch to 'Transactions' or 'Blocks' view and refresh. If RPC port differs, change GANACHE_RPC variable.")
