# Personal Finance App

A comprehensive, single-user personal finance management application built with **Python**, **Streamlit**, and **Google Firestore**.

## Features

- **Monthly View**: Detailed breakdown of Income, Fixed Expenses, Budgets, Real Expenses, and Extra Incomes.
- **Dashboard**: High-level snapshot with visual cash flow charts and real-time budget tracking.
- **Dynamic Entities**: Fully functional management of Banks, Accounts, Categories, Salaries (including complex tax deductions), Budgets, and Fixed Expenses.
- **Credit card purchases**: reserved in the projection (purchase month or charge month), hit Real only when the debt is settled from the Monthly View.
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

### 4. Running the tests
```bash
pip install -r requirements-dev.txt
pytest
```
All business logic lives in `services/finance_core.py` (pure Python, no Streamlit/Firestore),
so every rule can be tested with in-memory data. `services/finance_engine.py` only adds caching.

### 5. Running Locally
Simply run:
```bash
streamlit run app.py
```

## Per-deployment settings (secrets)

Besides the `[firebase]` credentials, each deployment can set:

```toml
[app]
min_managed_month = "2026-02"   # first month of the carry-over chain (YYYY-MM)
```

Months at or before it start with no carry-over. Set it to the month you start
recording data. Invalid or missing values fall back to `2026-02`.

## Sharing the app with someone else

Each person needs **their own deployment with their own Firebase project**: the
app is single-user and has no login, so two people on one deployment see and
edit the same data. Ideally they fork the repo and deploy from their own
Streamlit account, so their service-account key lives only in their secrets.

## Deploying to Streamlit Cloud

1. Push this entire repository to GitHub.
2. Go to [Streamlit Community Cloud](https://share.streamlit.io/) and log in.
3. Click **New app** and select your repository, branch, and `app.py` file.
4. Click **Advanced settings** before deploying, and paste the contents of your `secrets.toml` into the **Secrets** section.
5. Click **Deploy!**

Your application will be live, connected to your Firestore database, and optimized for personal finance tracking.
