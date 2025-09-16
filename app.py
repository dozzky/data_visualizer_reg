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
            if "T" in s:
                dt = datetime.fromisoformat(s)
                return dt.hour + dt.minute / 60.0 + dt.second / 3600.0 + dt.microsecond / 3_600_000_000.0
            # try HH:MM:SS
            try:
                t = datetime.strptime(s, "%H:%M:%S")
                return t.hour + t.minute / 60.0 + t.second / 3600.0
            except Exception:
                pass
            # try float with comma
            return float(s.replace(",", "."))
        except Exception:
            try:
                return float(s.replace(",", "."))
            except Exception:
                return 0.0
    # fallback
    return 0.0


# ---------------------------
# Загрузка данных
# ---------------------------

uploaded_file = st.file_uploader("Загрузите JSON файл со списком записей (или один объект)", type=["json"]) 

if not uploaded_file:
    st.info("Загрузите JSON-файл в левом верхнем углу — пример структуры в описании задачи.")
    st.stop()

try:
    raw = json.load(uploaded_file)
except Exception as e:
    st.error(f"Ошибка при чтении JSON: {e}")
    st.stop()

# Нормализация в DataFrame
if isinstance(raw, dict):
    df = pd.json_normalize([raw])
elif isinstance(raw, list):
    df = pd.json_normalize(raw)
else:
    st.error("Ожидался объект JSON или список объектов JSON")
    st.stop()

# Приводим колонку Дата в datetime
if "Дата" not in df.columns:
    st.error("В JSON отсутствует поле 'Дата'")
    st.stop()

df["Дата"] = pd.to_datetime(df["Дата"], errors="coerce")

# Сайдбар — фильтры
st.sidebar.header("Фильтры")
min_date = df["Дата"].min().date()
max_date = df["Дата"].max().date()

# По умолчанию берём полный диапазон
period = st.sidebar.date_input("Период (выберите 2 даты для диапазона)", value=(min_date, max_date))

# Если пользователь выбрал одну дату — преобразуем в диапазон из одной даты
if isinstance(period, (list, tuple)) and len(period) == 2:
    start_date, end_date = period[0], period[1]
else:
    start_date = end_date = period

# Смена / Оборудование / Топливо
shift_options = df["Смена"].dropna().unique().tolist() if "Смена" in df.columns else []
equip_options = df["Оборудование"].dropna().unique().tolist() if "Оборудование" in df.columns else []
fuel_options = df["Топливо"].dropna().unique().tolist() if "Топливо" in df.columns else []

selected_shifts = st.sidebar.multiselect("Смена", shift_options, default=shift_options)
selected_equips = st.sidebar.multiselect("Оборудование", equip_options, default=equip_options)
selected_fuels = st.sidebar.multiselect("Топливо", fuel_options, default=fuel_options)

# Применяем фильтры
filtered = df.copy()
filtered = filtered[(filtered["Дата"].dt.date >= start_date) & (filtered["Дата"].dt.date <= end_date)]
if selected_shifts:
    filtered = filtered[filtered["Смена"].isin(selected_shifts)]
if selected_equips:
    filtered = filtered[filtered["Оборудование"].isin(selected_equips)]
if selected_fuels:
    filtered = filtered[filtered["Топливо"].isin(selected_fuels)]

st.subheader("Отфильтрованные записи")
st.write(f"Период: {start_date} — {end_date} ({(end_date - start_date).days + 1} дн.)")
st.dataframe(filtered)

if filtered.empty:
    st.warning("Нет данных для выбранных фильтров")
    st.stop()

# ---------------------------
# Расчёты
# ---------------------------
# Календарный фонд T_k = количество дней в выбранном периоде * 24
days_count = (end_date - start_date).days + 1
T_k = days_count * 24.0

# 1) K_kf по каждому оборудованию (T_f суммируется по всем сменам и датам для оборудования)
k_kf_rows = []
for equip, grp in filtered.groupby("Оборудование"):
    T_f = 0.0
    # для каждой записи строки суммируем продолжительности, где включен двигатель
    for _, row in grp.iterrows():
        raw_durs = ensure_list(row.get("ПоказателиОборудованияПоУчасткамПродолжительность", []))
        raw_incs = ensure_list(row.get("ПоказателиОборудованияПоУчасткамВключенДвигатель", []))

        hours = [duration_hours_from_item(x) for x in raw_durs]
        # если длины списков не совпадают — обрезаем по минимальной длине
        n = min(len(hours), len(raw_incs)) if raw_incs else len(hours)
        if n == 0 and hours:
            # нет данных о включении -> считаем что всё не включено
            pass
        else:
            for i in range(n):
                if to_bool(raw_incs[i]):
                    T_f += hours[i]

    k = T_f / T_k if T_k > 0 else np.nan
    k_kf_rows.append({
        "Оборудование": equip,
        "Тк (ч)": round(T_k, 2),
        "Тф (ч)": round(T_f, 2),
        "Ккф": round(k, 3)
    })

k_kf_df = pd.DataFrame(k_kf_rows).sort_values("Ккф", ascending=False)

# 2) K_is_vr — для каждой пары (Оборудование, Смена)
k_is_rows = []
for (equip, shift), grp in filtered.groupby(["Оборудование", "Смена"]):
    T_sm = 0.0
    T_sm_f = 0.0
    for _, row in grp.iterrows():
        raw_durs = ensure_list(row.get("ПоказателиОборудованияПоУчасткамПродолжительность", []))
        raw_incs = ensure_list(row.get("ПоказателиОборудованияПоУчасткамВключенДвигатель", []))

        hours = [duration_hours_from_item(x) for x in raw_durs]
        n = min(len(hours), len(raw_incs)) if raw_incs else len(hours)
        # Суммируем общее время
        T_sm += sum(hours)
        # Суммируем рабочее время (engine on)
        if n > 0:
            for i in range(n):
                if to_bool(raw_incs[i]):
                    T_sm_f += hours[i]
        else:
            # если нет данных о включении — считаем, что двигатель выключен -> ничего не добавляем
            pass

    kis = (T_sm_f / T_sm) if T_sm > 0 else np.nan
    k_is_rows.append({
        "Оборудование": equip,
        "Смена": shift,
        "Тсм (ч)": round(T_sm, 2),
        "Тсмф (ч)": round(T_sm_f, 2),
        "Кисвр": round(kis, 3)
    })

k_is_df = pd.DataFrame(k_is_rows).sort_values(["Оборудование", "Смена"])

# ---------------------------
# Вывод результатов
# ---------------------------
st.subheader("📈 Коэффициент использования календарного фонда (Ккф) — по оборудованию")
st.dataframe(k_kf_df)

# Кнопка скачать
csv_k_kf = k_kf_df.to_csv(index=False).encode("utf-8")
st.download_button("Скачать Ккф (CSV)", csv_k_kf, file_name="k_kf_by_equipment.csv")

st.subheader("📈 Коэффициент использования оборудования по времени (Кисвр) — по оборудованию и сменам")
st.dataframe(k_is_df)
csv_k_is = k_is_df.to_csv(index=False).encode("utf-8")
st.download_button("Скачать Кисвр (CSV)", csv_k_is, file_name="k_is_by_equipment_shift.csv")

# ---------------------------
# Графики
# ---------------------------
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.markdown("#### Гистограмма: Ккф по оборудованию")
    if not k_kf_df.empty:
        chart1 = alt.Chart(k_kf_df).mark_bar().encode(
            x=alt.X("Оборудование:N", sort="-y", title=None),
            y=alt.Y("Ккф:Q", title="Ккф"),
            tooltip=["Оборудование", "Тф (ч)", "Тк (ч)", "Ккф"]
        ).properties(height=400)
        st.altair_chart(chart1, use_container_width=True)
    else:
        st.info("Нет данных для построения графика Ккф")

with col2:
    st.markdown("#### Гистограмма: Кисвр по оборудованию (разбитие по сменам)")
    if not k_is_df.empty:
        # Уберём NaN Кисвр для визуализации (или покажем 0)
        vis_df = k_is_df.copy()
        vis_df["Кисвр"] = vis_df["Кисвр"].fillna(0)

        chart2 = alt.Chart(vis_df).mark_bar().encode(
            x=alt.X("Оборудование:N", title=None),
            y=alt.Y("Кисвр:Q", title="Кисвр"),
            color=alt.Color("Смена:N", title="Смена"),
            tooltip=["Оборудование", "Смена", "Тсм (ч)", "Тсмф (ч)", "Кисвр"],
            xOffset="Смена:N"
        ).properties(height=400)

        st.altair_chart(chart2, use_container_width=True)
    else:
        st.info("Нет данных для построения графика Кисвр")

st.caption("Примечание: Тк рассчитывается как количество дней в выбранном диапазоне * 24ч.\nКисвр рассчитывается отдельно для каждой пары (Оборудование, Смена) — суммируются продолжительности и продолжительности с включённым двигателем внутри этой пары.")
