import streamlit as st
import pandas as pd
import json
from datetime import datetime

st.set_page_config(page_title="Анализ работы оборудования", layout="wide")

st.title("📊 Анализ работы оборудования")

# Загрузка JSON файла
uploaded_file = st.file_uploader("Загрузите JSON файл", type="json")

if uploaded_file:
    data = json.load(uploaded_file)
    
    # Если загружен список объектов - нормализуем
    if isinstance(data, dict):
        df = pd.json_normalize(data)
    elif isinstance(data, list):
        df = pd.json_normalize(data)
    else:
        st.error("Некорректный формат JSON")
        st.stop()
    
    # Преобразуем дату
    df["Дата"] = pd.to_datetime(df["Дата"], errors="coerce")

    # Фильтры
    st.sidebar.header("Фильтры")

    min_date = df["Дата"].min().date()
    max_date = df["Дата"].max().date()
    period = st.sidebar.date_input("Период", [min_date, max_date])

    смена = st.sidebar.multiselect("Смена", df["Смена"].unique())
    оборудование = st.sidebar.multiselect("Оборудование", df["Оборудование"].unique())
    топливо = st.sidebar.multiselect("Топливо", df["Топливо"].unique())

    # Применяем фильтры
    filtered_df = df.copy()

    if len(period) == 2:
        start, end = period
        filtered_df = filtered_df[(filtered_df["Дата"].dt.date >= start) & (filtered_df["Дата"].dt.date <= end)]

    if смена:
        filtered_df = filtered_df[filtered_df["Смена"].isin(смена)]
    if оборудование:
        filtered_df = filtered_df[filtered_df["Оборудование"].isin(оборудование)]
    if топливо:
        filtered_df = filtered_df[filtered_df["Топливо"].isin(топливо)]

    st.subheader("Отфильтрованные данные")
    st.dataframe(filtered_df)

    # -------------------
    # Расчеты по оборудованию
    # -------------------
    if not filtered_df.empty:
        results = []

        # Календарный фонд (одинаков для всех)
        days_count = (filtered_df["Дата"].dt.date.nunique())
        T_k = days_count * 24

        for equip, group in filtered_df.groupby("Оборудование"):
            T_f = 0
            T_sm = 0
            T_sm_f = 0

            for idx, row in group.iterrows():
                durations = [datetime.fromisoformat(x) for x in row["ПоказателиОборудованияПоУчасткамПродолжительность"]]
                durations_hours = [(d.hour + d.minute/60) for d in durations]
                includes = row["ПоказателиОборудованияПоУчасткамВключенДвигатель"]

                # Сумма всех продолжительностей
                T_sm += sum(durations_hours)
                # Сумма, когда двигатель включен
                T_f += sum([dur for dur, inc in zip(durations_hours, includes) if inc])
                T_sm_f += sum([dur for dur, inc in zip(durations_hours, includes) if inc])

            # Коэффициенты
            K_kf = T_f / T_k if T_k > 0 else 0
            K_is_vr = T_sm_f / T_sm if T_sm > 0 else 0

            results.append({
                "Оборудование": equip,
                "Календарный фонд (Тк), ч": round(T_k, 2),
                "Фактическое время работы (Тф), ч": round(T_f, 2),
                "Суммарное время (Тсм), ч": round(T_sm, 2),
                "Рабочее время в смене (Тсмф), ч": round(T_sm_f, 2),
                "Коэф. использования календарного фонда (Ккф)": round(K_kf, 3),
                "Коэф. использования по времени (Кисвр)": round(K_is_vr, 3),
            })

        results_df = pd.DataFrame(results)

        st.subheader("📈 Расчеты по оборудованию")
        st.dataframe(results_df)

    else:
        st.warning("Нет данных для выбранных фильтров")
