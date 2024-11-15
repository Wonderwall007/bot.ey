from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
import logging
import os
import re
from keep_alive import keep_alive
keep_alive(
    
# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)

# Your bot's token
BOT_TOKEN = "8038156264:AAE6y8_i6hqcW849lmVtSahLplcxQTfCDos"

# Telethon API credentials
API_ID = 2040
API_HASH = 'b18441a1ff607e10a989891a5462e627'

# Create an instance of the Telegram Client for the bot
application = Application.builder().token(BOT_TOKEN).build()

# Dictionary to store user data
user_data = {}

def sanitize_phone_number(phone_number: str) -> str:
    """Remove non-digit characters from phone number for file naming."""
    return re.sub(r'\D', '', phone_number)

def get_option_keyboard():
    """Generate an inline keyboard with 'Next' button."""
    keyboard = [
        [InlineKeyboardButton('Next', callback_data='next')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: CallbackContext) -> None:
    """Initiate the bot conversation."""
    await update.message.reply_text(
        '👋😎 Welcome to the **Ultimate OTP Bot**! 🎉🎉\n'
        'Before we get started, make sure to join our awesome channel 👉 [@cheattoolssc] 👈 💥💥\n'
        'Now, send me your phone number 📱 (without +) eg. 918273637483 (without containing + sign) 🚀\n.'
    )

async def stop(update: Update, context: CallbackContext) -> None:
    """Stop the session creation process and clean up any leftover files."""
    user_id = update.message.from_user.id
    if user_id in user_data:
        if 'client' in user_data[user_id]:
            client = user_data[user_id]['client']
            if client.is_connected():
                await client.disconnect()
                logging.debug(f'Client disconnected for user {user_id}.')
        
        # Clean up any leftover session files
        phone_number = user_data[user_id].get('phone')
        if phone_number:
            session_file_name = f'{sanitize_phone_number(phone_number)}.session'
            temp_session_file_name = f'session_{user_id}.session'
            
            # Remove the session files if they exist
            for file_name in [session_file_name, temp_session_file_name]:
                if os.path.isfile(file_name):
                    try:
                        os.remove(file_name)
                        logging.debug(f'Session file {file_name} removed.')
                    except Exception as cleanup_error:
                        logging.error(f'Error removing session file {file_name}: {str(cleanup_error)}')

        user_data.pop(user_id, None)  # Remove user data
        await update.message.reply_text('The session creation process has been stopped.')
    else:
        await update.message.reply_text('No active session to stop.')

async def handle_message(update: Update, context: CallbackContext) -> None:
    """Handle user input and manage OTP, 2FA, and session creation."""
    user_id = update.message.from_user.id
    text = update.message.text

    # Check for 'Stop' command
    if text.lower() == 'stop':
        await stop(update, context)
        return

    if text.isdigit() and 'phone' not in user_data.get(user_id, {}):
        user_data[user_id] = {'phone': text, 'otp': None}
        await update.message.reply_text(f'OTP has been sent to {text}. Please reply with the OTP or type "Stop" to end the process.')

        # Create and start the Telethon client
        client = TelegramClient(f'session_{user_id}', API_ID, API_HASH)
        user_data[user_id]['client'] = client
        await client.connect()
        
        # Send OTP request
        try:
            logging.debug(f'Sending OTP request to {text}')
            await client.send_code_request(text)
            logging.debug('OTP request sent')
        except Exception as e:
            await update.message.reply_text(f'Error sending OTP: {str(e)}')
            logging.error(f'Error sending OTP: {str(e)}')
            await client.disconnect()  # Disconnect client if there was an error
            user_data.pop(user_id, None)  # Clean up user data
            return
    
    elif text.isdigit() and 'otp' in user_data.get(user_id, {}):
        otp = text
        client = user_data[user_id].get('client')

        # Ensure the client is connected before proceeding
        if not client or not client.is_connected():
            await update.message.reply_text('Session expired or invalid. Please restart the process.')
            return
        
        try:
            # Verify OTP
            logging.debug(f'Verifying OTP: {otp}')
            await client.sign_in(user_data[user_id]['phone'], otp)
            
            # Check if 2FA is enabled
            try:
                await client.sign_in(password='')  # This will prompt for a password if 2FA is enabled
                user_data[user_id]['client'] = client
                await update.message.reply_text('2FA is enabled. Please enter your 2FA password or type "Stop" to end the process.')
                user_data[user_id]['awaiting_password'] = True
            except SessionPasswordNeededError:
                # No 2FA password required
                await update.message.reply_text('Login successful. Sending your session file.')
                await send_session_file(update, user_id)
        except SessionPasswordNeededError:
            # 2FA is enabled, prompt for password
            await update.message.reply_text('2FA is enabled. Please enter your 2FA password or type "Stop" to end the process.')
            user_data[user_id]['awaiting_password'] = True
        except Exception as e:
            await update.message.reply_text(f'Error verifying OTP: {str(e)}')
            logging.error(f'Error verifying OTP: {str(e)}')
            # Disconnect client if there was an error
            if client.is_connected():
                await client.disconnect()

    elif 'awaiting_password' in user_data.get(user_id, {}):
        password = text
        client = user_data[user_id].get('client')

        # Ensure the client is connected before proceeding
        if not client or not client.is_connected():
            await update.message.reply_text('Session expired or invalid. Please restart the process.')
            return
        
        try:
            await client.sign_in(password=password)
            await update.message.reply_text('Login successful. Sending your session file.')
            await send_session_file(update, user_id)
        except Exception as e:
            logging.error(f'Error logging in with 2FA: {str(e)}')
            # Only log error, don't send message for "readonly database"
            if "attempt to write a readonly database" not in str(e):
                await update.message.reply_text(f'Error logging in with 2FA: {str(e)}')

async def handle_button_click(update: Update, context: CallbackContext) -> None:
    """Handle button clicks for 'Next'."""
    query = update.callback_query
    user_id = query.from_user.id

    if query.data == 'next':
        # Automatically restart the process for a new session file
        user_data.pop(user_id, None)  # Remove any existing user data
        await query.message.reply_text('Please send me your phone number to start the verification process.')
    
    await query.answer()

async def send_session_file(update: Update, user_id: int) -> None:
    """Send the Telethon session file to the user and provide the option to create a new session."""
    user_info = user_data.get(user_id, {})
    client = user_info.get('client')
    phone_number = user_info.get('phone')
    
    if not client or not phone_number:
        await update.message.reply_text('No active session or phone number available.')
        return

    # Format the session file name based on the sanitized phone number
    session_file_name = f'{sanitize_phone_number(phone_number)}.session'
    temp_session_file_name = f'session_{user_id}.session'
    
    try:
        # Save the session file
        client.session.save()
        logging.debug(f'Saving session file as {temp_session_file_name}')
        
        # Check if the file was created
        if not os.path.isfile(temp_session_file_name):
            await update.message.reply_text('Session file was not created successfully.')
            logging.error('Session file was not created.')
            return

        # Rename the file
        os.rename(temp_session_file_name, session_file_name)

        # Send the session file
        with open(session_file_name, 'rb') as file:
            await update.message.reply_document(file, caption='Here is your Telethon session file.')
        
        # Clean up
        try:
            if os.path.isfile(session_file_name):
                os.remove(session_file_name)
                logging.debug(f'Session file {session_file_name} removed.')
            else:
                logging.warning(f'Session file {session_file_name} does not exist for removal.')
        except Exception as cleanup_error:
            logging.error(f'Error removing session file: {str(cleanup_error)}')

        # Offer the option to create another session
        await update.message.reply_text(
            'Session file created successfully. Click "Next" to create another session file.',
            reply_markup=get_option_keyboard()
        )

    except Exception as e:
        await update.message.reply_text(f'Error sending session file: {str(e)}')
        logging.error(f'Error sending session file: {str(e)}')
    finally:
        if client.is_connected():
            await client.disconnect()
        user_data.pop(user_id, None)  # Reset user data after successful session creation

def main() -> None:
    """Run the bot."""
    # Handlers for commands and messages
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_button_click))

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()
