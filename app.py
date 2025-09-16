import streamlit as st
import pandas as pd
import json
import altair as alt
import numpy as np
from datetime import datetime, timedelta
from typing import Any


st.set_page_config(page_title="Анализ работы оборудования — по сменам", layout="wide")


st.title("📊 Анализ использования оборудования — Ккф и Кисвр (по сменам)")


# ---------------------------
# Утилиты
# ---------------------------


def ensure_list(x: Any):
"""Привести значение к списку: если это строка-JSON -> распарсить, если простая строка -> [строка], если NaN -> []."""
if pd.isna(x):
return []
if isinstance(x, list):
return x
if isinstance(x, (tuple, set)):
return list(x)
if isinstance(x, str):
s = x.strip()
# Попытка распарсить JSON-представление списка
if s.startswith("[") and s.endswith("]"):
try:
return json.loads(s)
except Exception:
pass
# Если строка вида 'True'/'False' или простая строка - возвращаем как единственный элемент
return [x]
return [x]




def to_bool(x: Any) -> bool:
if isinstance(x, bool):
return x
if isinstance(x, (int, float)):
return x != 0
if isinstance(x, str):
s = x.strip().lower()
return s in ("true", "1", "yes", "y", "t")
return False




def duration_hours_from_item(item: Any) -> float:
"""Попытаться получить часы из разных форматов:
- число -> считаем как часы
- строка формата '0001-01-01T05:00:00' -> используем время (5ч)
- строка формата 'HH:MM:SS' -> перевод в часы
- строка с дробным числом -> float
В остальных случаях возвращаем 0.0
"""
if item is None:
return 0.0
# числовой
if isinstance(item, (int, float)):
try:
return float(item)
except Exception:
return 0.0
# строка
if isinstance(item, str):
s = item.strip()
if s == "":
return 0.0
# iso-like with dateTtime
try:
