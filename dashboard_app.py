# dashboard_app.py
import streamlit as st
import asyncio
import time
from web3 import Web3
from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware
from telegram import Bot
from collections import deque
import pandas as pd

# Try to import plotly; fallback to built-in charts if not installed
try:
    import plotly.express as px
    _HAS_PLOTLY = True
except Exception:
    _HAS_PLOTLY = False

# ---------------- Configuration ----------------
TOKEN = "7494163279:AAHIXZkCLLuaSeWMtLwRfH6dkzTiJ46l6RE"
CHAT_ID = 6435594534
bot = Bot(token=TOKEN)

GANACHE_RPC = "http://127.0.0.1:7545"

# Development-only account & key
TARGET_ACCOUNT = "0x1De19Dd4314B3bcb50bE2accaf661cA5E05e16bd"
TARGET_PRIVATE_KEY = "0x16ffabb1a0200871ba6fa464d577206da6918a014e1fa293ac4ddbedcb3dbe87"

GAS_THRESHOLD = 200
TEMP_THRESHOLD = 40
MAX_HISTORY = 100
# ------------------------------------------------

def normalize_privkey(pk: str) -> str:
    return pk[2:] if pk.startswith("0x") else pk

async def send_telegram_alert(message: str):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
    except Exception as e:
        st.error(f"Telegram send error (non-fatal): {e}")

# Connect to Ganache
w3 = Web3(Web3.HTTPProvider(GANACHE_RPC))
try:
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
except Exception:
    pass

st.set_page_config(page_title="Smart Sensor Dashboard", layout="wide")
st.title("🚨 Smart Sensor Alert System Dashboard (Simulation)")

if not w3.is_connected():
    st.error("❌ Cannot connect to Ganache RPC. Make sure Ganache is running on port 7545.")
    st.stop()
st.success("✅ Connected to Ganache blockchain")

TARGET_PRIVATE_KEY = normalize_privkey(TARGET_PRIVATE_KEY)

# ---------------- Session state ----------------
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

# ---------------- Accounts Info ----------------
with st.container():
    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown("### 🏷 Target Account")
        st.code(TARGET_ACCOUNT)
        try:
            bal = w3.eth.get_balance(TARGET_ACCOUNT)
            st.write("**Balance:**", f"{w3.from_wei(bal, 'ether')} ETH")
        except Exception as e:
            st.write("Balance error:", e)
    with c2:
        st.markdown("### 🔎 Ganache unlocked accounts (first 6)")
        try:
            for i, a in enumerate(w3.eth.accounts[:6]):
                st.write(f"{i}: {a}")
        except Exception:
            st.write("Cannot list Ganache accounts")

st.markdown("---")

# ---------------- Helper functions ----------------
def load_blockchain_logs():
    lines = []
    try:
        top = w3.eth.block_number
        for block_num in range(0, top + 1):
            block = w3.eth.get_block(block_num, full_transactions=True)
            for tx in block.transactions:
                lines.append({
                    "Block": block_num,
                    "Tx Hash": tx.hash.hex(),
                    "From": tx['from'],
                    "To": tx['to'],
                    "Value (ETH)": float(w3.from_wei(tx['value'], 'ether')),
                    "Data (hex)": tx.input if hasattr(tx, 'input') else (tx['input'] if 'input' in tx else "")
                })
    except Exception as e:
        st.warning(f"Cannot fetch blockchain logs: {e}")
    return lines

def send_blockchain_tx(message: str) -> (bool, str):
    """Send a transaction to log a message safely."""
    try:
        balance = w3.eth.get_balance(TARGET_ACCOUNT)
        gas_price = w3.to_wei(1, 'gwei')
        gas_limit = 100_000

        min_gas_cost = gas_limit * gas_price
        if balance < min_gas_cost:
            if len(w3.eth.accounts) > 0:
                funder = w3.eth.accounts[0]
                tx_fund = {
                    "from": funder,
                    "to": TARGET_ACCOUNT,
                    "value": w3.to_wei(1, "ether"),
                    "gas": 21000,
                    "gasPrice": gas_price
                }
                tx_hash_fund = w3.eth.send_transaction(tx_fund)
                w3.eth.wait_for_transaction_receipt(tx_hash_fund, timeout=30)
                time.sleep(0.3)
            else:
                return False, "Target account has insufficient ETH and no unlocked account available."

        nonce = w3.eth.get_transaction_count(TARGET_ACCOUNT)
        tx = {
            "nonce": nonce,
            "to": TARGET_ACCOUNT,
            "value": 0,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "chainId": w3.eth.chain_id,
            "data": Web3.to_hex(text=message)
        }

        signed = w3.eth.account.sign_transaction(tx, private_key=TARGET_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

        st.session_state.tx_history.append({
            "Block": receipt.blockNumber,
            "Tx Hash": tx_hash.hex(),
            "Message": message
        })
        return True, tx_hash.hex()
    except Exception as e:
        return False, str(e)

# ---------------- Tab 1: Sensors ----------------
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

    st.session_state.gas_history.append(gas_value)
    st.session_state.temp_history.append(temp_value)

    df_gas = pd.DataFrame({"Gas": list(st.session_state.gas_history)})
    df_temp = pd.DataFrame({"Temp": list(st.session_state.temp_history)})

    if _HAS_PLOTLY:
        st.plotly_chart(px.line(df_gas, y="Gas", title="Gas Levels"), use_container_width=True)
        st.plotly_chart(px.line(df_temp, y="Temp", title="Temperature"), use_container_width=True)
    else:
        st.line_chart(df_gas)
        st.line_chart(df_temp)

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
        st.success("✅ All sensors normal.")

    if alert_triggered and not st.session_state.alert_state:
        st.session_state.alert_state = True
        asyncio.run(send_telegram_alert(alert_message))
        ok, result = send_blockchain_tx(alert_message)
        if ok:
            st.success(f"Logged to blockchain: {result}")
        else:
            st.error(f"Blockchain TX failed: {result}")
        st.session_state.alert_history.append({"Time": time.strftime("%H:%M:%S"), "Type": "Alert", "Message": alert_message})
    elif not alert_triggered and st.session_state.alert_state:
        st.session_state.alert_state = False
        back_msg = "✅ All sensors back to normal."
        asyncio.run(send_telegram_alert(back_msg))
        ok, result = send_blockchain_tx(back_msg)
        if ok:
            st.success(f"Logged to blockchain: {result}")
        else:
            st.error(f"Blockchain TX failed: {result}")
        st.session_state.alert_history.append({"Time": time.strftime("%H:%M:%S"), "Type": "Normal", "Message": back_msg})

# ---------------- Tab 2: Alerts History ----------------
with tab2:
    st.subheader("📋 Alerts History")
    if st.session_state.alert_history:
        st.dataframe(pd.DataFrame(st.session_state.alert_history))
    else:
        st.info("No alerts yet.")

# ---------------- Tab 3: Blockchain Logs ----------------
with tab3:
    st.subheader("📜 Blockchain Transactions")
    if st.button("Refresh blockchain logs"):
        logs = load_blockchain_logs()
        if logs:
            st.dataframe(pd.DataFrame(logs))
        else:
            st.info("No transactions or unable to fetch logs.")

    if st.session_state.tx_history:
        st.markdown("**TXs sent by this dashboard**")
        st.dataframe(pd.DataFrame(st.session_state.tx_history))
    else:
        st.info("No dashboard-sent transactions yet.")
