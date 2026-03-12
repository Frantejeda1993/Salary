# Personal Finance App

A comprehensive, single-user personal finance management application built with **Python**, **Streamlit**, and **Google Firestore**.

## Features

- **Monthly View**: Detailed breakdown of Income, Fixed Expenses, Budgets, Real Expenses, and Extra Incomes.
- **Dashboard**: High-level snapshot with visual cash flow charts and real-time budget tracking.
- **Dynamic Entities**: Fully functional management of Banks, Accounts, Categories, Salaries (including complex tax deductions), Budgets, and Fixed Expenses.
- **Real & Projected Balances**: Seamlessly differentiate between your actual money in the bank vs what your balance will look like after paying upcoming obligations.

## Setup Instructions

### 1. Install Dependencies
Ensure you have Python 3.10+ installed. Install the requirements:
```bash
pip install -r requirements.txt
```

### 2. Configure Google Firestore
You must have a Firebase/Google Cloud project with Firestore enabled.
1. Go to your [Firebase Console](https://console.firebase.google.com/).
2. Create a new project or select an existing one.
3. Enable **Firestore Database** in **Native mode**.
4. Set up security rules (for local/single-user, `allow read, write: if true;` is acceptable during testing, but lock it down if deploying).
5. Go to **Project Settings** > **Service Accounts** > **Generate new private key**.
6. Download the JSON file.

### 3. Local Secrets Configuration
1. Rename `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
2. Open the file and copy the values from your downloaded JSON credential file into the corresponding fields in the `[firebase]` section. Pay special attention to formatting the `private_key` correctly with `\n` characters for newlines.

### 4. Running Locally
Simply run:
```bash
streamlit run app.py
```

## Deploying to Streamlit Cloud

1. Push this entire repository to GitHub.
2. Go to [Streamlit Community Cloud](https://share.streamlit.io/) and log in.
3. Click **New app** and select your repository, branch, and `app.py` file.
4. Click **Advanced settings** before deploying, and paste the contents of your `secrets.toml` into the **Secrets** section.
5. Click **Deploy!**

Your application will be live, connected to your Firestore database, and optimized for personal finance tracking.
