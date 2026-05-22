# Emergency Alert System 🚨

A browser-based emergency alert system that sends emergency notifications through Email, SMS, and WhatsApp with live location and camera capture support.

## Features

- 📧 Email emergency alerts
- 📱 SMS alerts using Twilio
- 💬 WhatsApp emergency notifications
- 📸 Camera image capture
- 📍 Live location sharing
- 🚨 Panic button support
- 🧠 AI-based gender detection
- 🌐 Browser-based interface

## Technologies Used

- Python
- Flask
- OpenCV
- Twilio API
- HTML
- CSS
- JavaScript

## Installation

Clone the repository:

```bash
git clone https://github.com/DhanushyaS01/Emergency-Alert-System.git
```

Move into the project folder:

```bash
cd Emergency-Alert-System
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run the Project

```bash
python app.py
```

Open in browser:

```text
http://localhost:5000
```

## Environment Variables

Create a `.env` file and add:

```env
SMTP_SENDER=your_email
SMTP_APP_PASSWORD=your_password
SMTP_RECEIVER=receiver_email

TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_token

TWILIO_FROM_NUMBER=your_number
TWILIO_TO_NUMBER=receiver_number
```

## Live Demo

https://women-safety-alert-system-il3a.onrender.com

## Deployment

Deployed using Render.

## License

This project is licensed under the MIT License.

## Author

Dhanushya S
