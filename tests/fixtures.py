"""Builders for in-memory datasets shaped like load_all_data()."""
import random
from datetime import datetime

EMPTY = ["accounts", "banks", "salaries", "overtimes", "expenses", "incomes", "transfers",
         "categories", "budgets", "fixed_expenses", "fixed_expense_instances",
         "monthly_account_snapshots", "credit_settlements"]


def empty_data() -> dict:
    return {k: [] for k in EMPTY}


def d(y, m, day=15) -> datetime:
    return datetime(y, m, day)


def random_dataset(seed: int) -> dict:
    rnd = random.Random(seed)
    data = empty_data()
    accs = ["main", "acc2", "acc3"]
    data["accounts"] = [
        {"id": a, "nombre": a, "is_main": a == "main", "saldo_inicial": rnd.choice([0.0, 500.0, 1234.5])}
        for a in accs
    ]
    data["categories"] = [
        {"id": "food", "nombre": "Food", "tipo": "normal"},
        {"id": "fun", "nombre": "Fun", "tipo": "normal"},
        {"id": "car", "nombre": "Car", "tipo": "normal"},
        {"id": "xtra", "nombre": "Extra", "tipo": "extra"},
    ]
    cats = [c["id"] for c in data["categories"]]
    for i in range(rnd.randint(1, 2)):
        sid = f"sal{i}"
        data["salaries"].append({
            "id": sid, "account_id": rnd.choice(["main", "main", "acc2"]),
            "salario_bruto": rnd.choice([1800.0, 2500.0, 3100.0]),
            "fecha_inicio": d(2026, rnd.randint(1, 3), 1),
            "fecha_fin": d(2026, rnd.randint(8, 12), 28) if rnd.random() < 0.3 else None,
            "deductions": [
                {"name": "SS", "percentage": 0.0635, "applies_to_extras": True},
                {"name": "IRPF", "percentage": rnd.choice([0.12, 0.15]), "applies_to_extras": rnd.random() < 0.5},
            ],
        })
        for _ in range(rnd.randint(0, 3)):
            data["overtimes"].append({"salary_id": sid, "mes_aplicacion": f"2026-{rnd.randint(1, 12):02d}",
                                      "monto_bruto": float(rnd.randint(50, 400))})
    n = 0
    for _ in range(rnd.randint(10, 60)):
        n += 1
        data["expenses"].append({"id": f"e{n}", "account_id": rnd.choice(accs + ["main"] * 3),
                                 "categoria_id": rnd.choice(cats), "monto": float(rnd.randint(5, 600)),
                                 "fecha": d(2026, rnd.randint(1, 12), rnd.randint(1, 28))})
    for _ in range(rnd.randint(0, 10)):
        n += 1
        data["incomes"].append({"id": f"i{n}", "account_id": rnd.choice(accs),
                                "categoria_id": rnd.choice(cats + ["", ""]), "monto": float(rnd.randint(5, 300)),
                                "fecha": d(2026, rnd.randint(1, 12), rnd.randint(1, 28))})
    for _ in range(rnd.randint(0, 10)):
        n += 1
        o, t = rnd.sample(accs, 2)
        loan = rnd.random() < 0.3
        data["transfers"].append({
            "id": f"t{n}", "cuenta_origen": o, "cuenta_destino": t, "monto": float(rnd.randint(10, 500)),
            "fecha": d(2026, rnd.randint(1, 12), rnd.randint(1, 28)), "is_loan": loan,
            "status": rnd.choice(["pending", "paid"]),
            "descripcion": "Transferencia automatica gastos" if (o == "main" and rnd.random() < 0.5) else "x",
        })
    for i, c in enumerate(rnd.sample(cats[:3], rnd.randint(0, 3))):
        data["budgets"].append({"id": f"b{i}", "categoria_id": c, "account_id": rnd.choice(["main", "main", "acc2"]),
                                "monto": float(rnd.choice([100, 250, 400])),
                                "fecha_inicio": d(2026, rnd.randint(1, 4), 1),
                                "fecha_fin": d(2026, 11, 30) if rnd.random() < 0.3 else None})
    for i in range(rnd.randint(0, 5)):
        fid = f"f{i}"
        data["fixed_expenses"].append({"id": fid, "account_id": rnd.choice(accs), "monto": float(rnd.randint(20, 900)),
                                       "es_propio": rnd.random() < 0.4,
                                       "fecha_inicio": d(2026, rnd.randint(1, 3), 1),
                                       "fecha_fin": d(2026, rnd.randint(6, 12), 28) if rnd.random() < 0.3 else None})
        for m in range(1, 13):
            if rnd.random() < 0.5:
                data["fixed_expense_instances"].append({
                    "fixed_expense_id": fid, "mes": f"2026-{m:02d}", "estado": rnd.choice(["pagado", "impagado"]),
                    "monto": float(rnd.randint(20, 900)) if rnd.random() < 0.3 else None})
    return data
