import streamlit as st
import asyncio
import time
from web3 import Web3
from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware
from telegram import Bot

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

st.title("Smart Sensor Alert System Dashboard (Simulation)")

if not w3.is_connected():
    st.error("❌ Cannot connect to Ganache RPC. Make sure Ganache GUI is running on port 7545.")
    st.stop()
st.success("✅ Connected to Ganache blockchain")

TARGET_PRIVATE_KEY = normalize_privkey(TARGET_PRIVATE_KEY)

col1, col2 = st.columns(2)
with col1:
    st.write("**Target account**")
    st.write(TARGET_ACCOUNT)
with col2:
    try:
        bal = w3.eth.get_balance(TARGET_ACCOUNT)
        st.write("Balance:", f"{w3.from_wei(bal, 'ether')} ETH")
    except Exception as e:
        st.write("Balance: error", e)

st.markdown("---")
st.subheader("Simulated Sensors")

gas_value = st.slider("Gas Level", 0, 500, 100)
temp_value = st.slider("Temperature (°C)", 20, 50, 30)
tilt_status = st.selectbox("Tilt Status", ["Stable", "Tilt Detected"])

# Check conditions
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

# Handle alert
if alert_triggered:
    st.warning("⚠ Alert Active! Sending Telegram message & saving blockchain record...")
    asyncio.run(send_telegram_alert(alert_message))
    st.success("✅ Telegram alert sent!")

    try:
        target_balance = w3.eth.get_balance(TARGET_ACCOUNT)
        st.write(f"Target balance before tx: {w3.from_wei(target_balance, 'ether')} ETH")

        if target_balance < w3.to_wei(0.001, "ether"):
            st.info("Target account balance low. Funding from Ganache account[0]...")
            funder = w3.eth.accounts[0]
            tx_fund = {
                "from": funder,
                "to": TARGET_ACCOUNT,
                "value": AUTO_FUND_WEI,
                "gas": 21000,
                "gasPrice": w3.to_wei("1", "gwei")
            }
            tx_hash_fund = w3.eth.send_transaction(tx_fund)
            st.write("Funding tx sent:", tx_hash_fund.hex())
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash_fund, timeout=120)
            st.success("✅ Funding transaction mined.")
            time.sleep(1)
            target_balance = w3.eth.get_balance(TARGET_ACCOUNT)
            st.write(f"Target balance after funding: {w3.from_wei(target_balance, 'ether')} ETH")

        if target_balance >= w3.to_wei(0.0001, "ether"):
            nonce = w3.eth.get_transaction_count(TARGET_ACCOUNT)
            tx = {
                "nonce": nonce,
                "to": TARGET_ACCOUNT,
                "value": 0,
                "gas": 21000,
                "gasPrice": w3.to_wei("1", "gwei"),
                "chainId": w3.eth.chain_id
            }
            signed = w3.eth.account.sign_transaction(tx, private_key=TARGET_PRIVATE_KEY)
            raw_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            st.success(f"✅ Blockchain record saved: {raw_hash.hex()}")
        else:
            st.error("❌ Insufficient funds to pay gas. Please fund target manually in Ganache.")
    except Exception as e:
        st.error(f"❌ Transaction error: {e}")
else:
    st.success("✅ All sensors normal and stable.")

# -------- Live transactions display --------
st.markdown("---")
st.subheader("Live Blockchain Transactions")

def display_all_transactions():
    tx_lines = []
    for block_num in range(w3.eth.block_number + 1):
        block = w3.eth.get_block(block_num, full_transactions=True)
        for tx in block.transactions:
            tx_lines.append(
                f"Block {block_num} | Tx Hash: {tx.hash.hex()} | From: {tx['from']} | To: {tx['to']} | Value: {w3.from_wei(tx['value'], 'ether')} ETH"
            )
    if tx_lines:
        st.text("\n".join(tx_lines))
    else:
        st.text("No transactions yet.")

display_all_transactions()
