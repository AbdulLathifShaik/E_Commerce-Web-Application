import os, smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()


def sendmail(to, subject, body):
    # Development mode: print the email in the terminal instead of sending it
    if os.getenv('MAIL_DEBUG') == '1':
        print('\n----- EMAIL (not sent, MAIL_DEBUG=1) -----')
        print('To:', to)
        print('Subject:', subject)
        print(body)
        print('------------------------------------------\n')
        return

    user = os.environ['MAIL_USER'].strip()
    password = os.environ['MAIL_APP_PASSWORD'].replace(' ', '').strip()
    msg = EmailMessage()
    msg['From'] = user
    msg['To'] = to
    msg['Subject'] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=20) as server:
            server.login(user, password)
            server.send_message(msg)
    except smtplib.SMTPServerDisconnected:
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=20) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)