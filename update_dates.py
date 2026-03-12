import os

replacements = {
    'st.date_input("Date", value=date.today())': 'st.date_input("Date", value=date.today(), format="DD/MM/YYYY")',
    'st.date_input("Date", value=tr.get("fecha", date.today()))': 'st.date_input("Date", value=tr.get("fecha", date.today()), format="DD/MM/YYYY")',
    'st.date_input("Date (Income)", value=date.today(), key="dt_inc")': 'st.date_input("Date (Income)", value=date.today(), key="dt_inc", format="DD/MM/YYYY")',
    'st.date_input("Date", value=exp.get("fecha", date.today()))': 'st.date_input("Date", value=exp.get("fecha", date.today()), format="DD/MM/YYYY")',
    'st.date_input("Date (Income)", value=inc.get("fecha", date.today()))': 'st.date_input("Date (Income)", value=inc.get("fecha", date.today()), format="DD/MM/YYYY")',
    'st.date_input("Start Date", value=date.today())': 'st.date_input("Start Date", value=date.today(), format="DD/MM/YYYY")',
    'st.date_input("End Date", value=date.today())': 'st.date_input("End Date", value=date.today(), format="DD/MM/YYYY")',
    'st.date_input("Start Date", value=fe.get("fecha_inicio", date.today()))': 'st.date_input("Start Date", value=fe.get("fecha_inicio", date.today()), format="DD/MM/YYYY")',
    'st.date_input("End Date", value=current_end if current_end else date.today())': 'st.date_input("End Date", value=current_end if current_end else date.today(), format="DD/MM/YYYY")',
    'st.date_input("Start Date", value=budget.get("fecha_inicio", date.today()))': 'st.date_input("Start Date", value=budget.get("fecha_inicio", date.today()), format="DD/MM/YYYY")',
}

files = ['pages/transfers.py', 'pages/transactions.py', 'pages/fixed_expenses.py', 'pages/budgets.py']
for fname in files:
    path = r"c:\Users\andre\Downloads\Salary\\" + fname
    with open(path, 'r', encoding='utf8') as f:
        content = f.read()
    
    for old, new in replacements.items():
        content = content.replace(old, new)
        
    with open(path, 'w', encoding='utf8') as f:
        f.write(content)
print("Updated all files")
