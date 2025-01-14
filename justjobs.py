import inspect
import json
import logging
import os
import re
import signal
import subprocess
import sys
import boto3
import uuid

from datetime import datetime, timedelta
from telegram import ReplyKeyboardMarkup
from telegram import ChatAction, ParseMode, Update
from telegram.ext import (CallbackContext, CommandHandler, Filters, MessageHandler, Updater)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO,
)


"""
---Process ID Management Starts---
This part of the code helps out when you want to run your program in the background using '&'. This will
save the process id of the program going in background in a file named 'pid'. Now when you run your
program again, last one will be terminated with help of pid. If in case the no process exists
with given process id, simply  pid file will be deleted and a new one with current pid will be
created.......
"""
currentPID = os.getpid()
if 'pid' not in os.listdir():
    with open('pid', mode='w') as f:
        print(str(currentPID), file=f)
else:
    with open('pid', mode='r') as f:
        try:
            os.kill(int(f.read()), signal.SIGTERM)
            logging.info(f'Terminating the previous instance of {os.path.realpath(__file__)}')
        except (ProcessLookupError, ValueError):
            subprocess.run(['rm', 'pid'])
    with open('pid', mode='w') as f:
        print(str(currentPID), file=f)
"""
---Process ID Management Ends---
""" 

"""
---Token Management Starts---
This part will check for the config.json file which holds  Telegram and Channel ID and will also
give a user-friendly message if they are invalid. A new file is created if not present in the project
directory....
"""
configError = (
    'Please open config.json file located in the project directory and replace the value "0" of '
    'Telegram-Bot-Token with Token you received from botfather.'
)
if 'config.json' not in os.listdir():
    with open('config.json', mode='w') as f:
        json.dump({'Telegram-Bot-Token': 0, 'Channel-Id': 0}, f)
        logging.info(configError)
        sys.exit(0)
else:
    with open('config.json', mode='r') as f:
        config = json.loads(f.read())
        if config['Telegram-Bot-Token']:
            logging.info('Token Present, continuing...')
            TelegramBotToken = config['Telegram-Bot-Token']
            if config['Channel-Id']:
                ChannelId = config['Channel-Id']
            else:
                logging.info((
                    'Channel ID is not present in config.json. Please follow the instruction on '
                    'README.md, run getid.py and replace the Channel ID you obtain.'
                ))
        else:
            logging.info(configError)
            sys.exit(0)
"""
---Token Management Ends---
"""

USER_STATES = {}
jobs_queue = {}
applicants_queue = {}
recruiters_queue = {}


updater = Updater(token="6953050320:AAEkOkS_sFuB7IddIKcNmf13uS1FI5P3P58")

dispatcher = updater.dispatcher



def start(update: Update, context: CallbackContext):
    context.bot.sendChatAction(chat_id=update.message.chat_id, action=ChatAction.TYPING)
    start_msg = inspect.cleandoc((
        'Hi there! Are you an *Applicant* or a *Recruiter*?\n'
        'Use /apply if you are an Applicant, and /recruit if you are a Recruiter.\n'
        'Use /help to get more information..'
    ))

    # Provide a one-time keyboard with the options 'Applicant' and 'Recruiter'
    keyboard = [['/apply', '/recruit']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

    update.message.reply_text(start_msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
def chooseProfile(update: Update, context: CallbackContext):
    context.bot.sendChatAction(chat_id=update.message.chat_id, action=ChatAction.TYPING)

    user_choice = update.message.text.lower()
    if user_choice == 'applicant':
        apply(update, context)
    elif user_choice == 'recruiter':
        recruit(update, context)
        # You can add your logic for handling recruiter subscription or any other actions here
        context.bot.send_message(
            chat_id=update.message.chat_id,
            text='To access recruiter features, please subscribe to our premium service.',
        )
    else:
        context.bot.send_message(
            chat_id=update.message.chat_id,
            text='Invalid choice. Please select either *Applicant* or *Recruiter*.',
            parse_mode=ParseMode.MARKDOWN,
        )

# AWS credentials
aws_access_key_id = "AKIA4SCY35W54RDN5UMM"
aws_secret_access_key = "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"
aws_region = "us-east-1"

# DynamoDB table name for recruiters
dynamodb_table_name_recruiter = "cued_bot2"

# DynamoDB table name for applicants
dynamodb_table_name_applicant = "cued_bot"

# Initialize DynamoDB resource
dynamodb = boto3.resource('dynamodb', region_name=aws_region, aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)
table_recruiter = dynamodb.Table(dynamodb_table_name_recruiter)
table_applicant = dynamodb.Table(dynamodb_table_name_applicant)
table_recruiter_subscription = dynamodb.Table('recruiter_subscription') 


def check_subscription_status(user_id):
    try:
        response = table_recruiter.get_item(Key={'user_id': str(user_id)})
        item = response.get('Item')

        if item:
            is_subscribed = item.get('is_subscribed', False)
            points_balance = item.get('points_balance', 0)
            
            # Check if subscription has expired
            subscription_date = item.get('subscription_date')
            if subscription_date:
                expiration_date = subscription_date + timedelta(days=90)  # Assuming 90 days subscription period
                if datetime.now() > expiration_date:
                    is_subscribed = False  # Subscription has expired
            else:
                # Assign 100 points if the user is new
                is_subscribed = True
                points_balance = 100
                subscription_date = int(datetime.now().timestamp())
                # Update DynamoDB with the new points and subscription date
                table_recruiter.put_item(
                    Item={
                        'telegram_user_id': str(user_id),
                        'user_id': str(user_id),
                        'is_subscribed': is_subscribed,
                        'points_balance': points_balance,
                        'subscription_date': subscription_date,
                    }
                )
            
            return is_subscribed, points_balance
        else:
            # Assign 100 points if the user is new
            is_subscribed = True
            points_balance = 100
            subscription_date = int(datetime.now().timestamp())
            # Update DynamoDB with the new points and subscription date
            table_recruiter.put_item(
                Item={
                    'telegram_user_id': str(user_id),
                    'user_id': str(user_id),
                    'is_subscribed': is_subscribed,
                    'points_balance': points_balance,
                    'subscription_date': subscription_date,
                }
            )
            return is_subscribed, points_balance
    except Exception as e:
        print(f"Error checking subscription status: {str(e)}")
        return False, 0


def recruit(update: Update, context: CallbackContext):
    context.bot.sendChatAction(chat_id=update.message.chat_id, action=ChatAction.TYPING)
    USER_STATES[update.message.chat_id] = 'recruit'

    # Check if the recruiter already has points (to avoid giving points every time they enter)
    is_subscribed, points_balance = check_subscription_status(update.message.from_user.id)

    if not is_subscribed:
        # Give 100 points to the recruiter
        points_balance = 100
        table_recruiter.put_item(
            Item={
                'telegram_user_id': str(update.message.from_user.id),
                'user_id': str(update.message.from_user.id),
                'is_subscribed': True,
                'points_balance': points_balance,
                'subscription_date': int(datetime.now().timestamp()),  # Store the subscription date
            }
        )

    # Retrieve the latest points_balance from the DynamoDB table
    is_subscribed, points_balance = check_subscription_status(update.message.from_user.id)

    if update.message.chat_id not in recruiters_queue:
        recruiters_queue[update.message.chat_id] = {'answers': [], 'resume_link': ''}

    context.bot.send_message(
        chat_id=update.message.chat_id,
        text=f'After submission, your details will be reviewed by recruiters. You have {points_balance} points.'
    )
    context.bot.send_message(chat_id=update.message.chat_id, text='What is your company name?')

    # Deduct 10 points from the recruiter's balance
    if is_subscribed:
        updated_points_balance = max(0, points_balance - 10)
        table_recruiter.update_item(
            Key={'user_id': str(update.message.from_user.id)},
            UpdateExpression='SET points_balance = :points',
            ExpressionAttributeValues={':points': updated_points_balance}
        )

        # Update the points_balance in the USER_STATES dictionary for real-time tracking
        USER_STATES[update.message.chat_id] = updated_points_balance



def apply(update: Update, context: CallbackContext):
    context.bot.sendChatAction(chat_id=update.message.chat_id, action=ChatAction.TYPING)
    USER_STATES[update.message.chat_id] = 'apply'
    if update.message.chat_id not in applicants_queue:
        applicants_queue[update.message.chat_id] = {'answers': [], 'resume_link': ''}
    context.bot.send_message(
        chat_id=update.message.chat_id,
        text='After submission, your details will be reviewed by recruiters. Use /help for more info.',
    )
    context.bot.send_message(chat_id=update.message.chat_id, text='What is your full name?')

def addDetails(update: Update, context: CallbackContext):
    context.bot.sendChatAction(chat_id=update.message.chat_id, action=ChatAction.TYPING)

    user_state = USER_STATES.get(update.message.chat_id, None)

    if user_state == 'apply' or user_state == 'recruit':
        queue = applicants_queue if user_state == 'apply' else recruiters_queue

        if update.message is not None and update.message.chat_id in queue:
            current_step = len(queue[update.message.chat_id]['answers'])

            if current_step == 0:
                queue[update.message.chat_id]['answers'].append(update.message.text)
                context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text='What is your company size?' if user_state == 'recruit' else 'What is your age?',
                )
            elif current_step == 1:
                queue[update.message.chat_id]['answers'].append(update.message.text)
                context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text='Office location / Remote work ?' if user_state == 'recruit' else 'What is your highest qualification?',
                )
            elif current_step == 2:
                queue[update.message.chat_id]['answers'].append(update.message.text)
                context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text='Which role you are looking for ?' if user_state == 'recruit' else 'What skills do you possess?',
                )
            elif current_step == 3:
                queue[update.message.chat_id]['answers'].append(update.message.text)
                context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text='provide emailid' if user_state == 'recruit' else 'What is your relevant work experience? (mention role and duration)',
                )
            elif current_step == 4:
                queue[update.message.chat_id]['answers'].append(update.message.text)
                context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text='Provide a link of company page' if user_state == 'recruit' else 'Provide a link to your resume/cv on Google Drive or any other cloud storage (e.g., Dropbox).'
                )
            elif current_step == 5:
                queue[update.message.chat_id]['answers'].append(update.message.text)
                context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text='Provide a link to company LinkedIn page.' if user_state == 'recruit' else 'Provide a link to your LinkedIn profile.'
                )
            elif current_step == 6:
                queue[update.message.chat_id]['answers'].append(update.message.text)

                # Process the gathered information
                full_name = queue[update.message.chat_id]['answers'][0]
                second_field = queue[update.message.chat_id]['answers'][1]
                third_field = queue[update.message.chat_id]['answers'][2]
                fourth_field = queue[update.message.chat_id]['answers'][3]
                fifth_field = queue[update.message.chat_id]['answers'][4]
                sixth_field = queue[update.message.chat_id]['answers'][5]
                seventh_field = queue[update.message.chat_id]['answers'][6]

                # Save user data to DynamoDB - update this based on your needs
                user_details = {
                    'telegram_user_id': str(update.message.from_user.id),
                    'user_id': str(update.message.from_user.id),
                    'Full Name': full_name,
                    'Second Field': second_field,
                    'Third Field': third_field,
                    'Fourth Field': fourth_field,
                    'Fifth Field': fifth_field,
                    'Sixth Field': sixth_field,
                    'Seventh Field': seventh_field,
                }
                table = table_recruiter if user_state == 'recruit' else table_applicant
                table.put_item(Item=user_details)

                # Generate message based on user type
                if user_state == 'recruit':
                    tg_msg = inspect.cleandoc(f"""
                        Recruiter Information:
                        Full Name: {full_name}
                        Company Size: {second_field}
                        Location: {third_field}
                        Skills Needed: {fourth_field}
                        Company Work: {fifth_field}
                        Company Page Link: [Click Here]({sixth_field})
                        LinkedIn Profile: [Click Here]({seventh_field})
                    """)
                else:
                    tg_msg = inspect.cleandoc(f"""
                        Applicant Information:
                        Name: {full_name}
                        Age: {second_field}
                        Highest Qualification: {third_field}
                        Skills: {fourth_field}
                        Experience: {fifth_field}
                        Resume Link: [Click Here]({sixth_field})
                        LinkedIn Profile: [Click Here]({seventh_field})
                    """)

                context.bot.send_message(
                    chat_id=ChannelId, text=tg_msg, parse_mode=ParseMode.MARKDOWN
                )
                context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text='Thank you. Your details have been submitted.' if user_state == 'recruit' else 'Thank you. Your application has been submitted. Recruiters will review your details.',
                )
                
                del queue[update.message.chat_id]

        elif update.message.chat.type == 'private':
            context.bot.send_message(
                chat_id=update.message.chat_id, text=f'Please use /{user_state} to submit {user_state} details.',
            )
    else:
        context.bot.send_message(
            chat_id=update.message.chat_id, text='Please use /apply or /recruit to submit applications.',
        )


dispatcher.add_handler(CommandHandler('apply', apply))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, addDetails))
dispatcher.add_handler(CommandHandler('recruit', recruit)) 
dispatcher.add_handler(CommandHandler('start', start))

updater.start_polling()
