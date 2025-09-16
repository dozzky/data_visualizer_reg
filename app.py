import streamlit as st
import pandas as pd
import json
from datetime import datetime
import plotly.express as px

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
        kkf_results = []   # таблица для Ккф
        kisvr_results = [] # таблица для Кисвр

        # Календарный фонд (одинаков для всех)
        days_count = filtered_df["Дата"].dt.date.nunique()
        T_k = days_count * 24

        # --- Ккф: считаем агрегировано по оборудованию и дате ---
        for (equip, date), group in filtered_df.groupby(["Оборудование", filtered_df["Дата"].dt.date]):
            T_f = 0

            for _, row in group.iterrows():
                durations = [datetime.fromisoformat(x) for x in row["ПоказателиОборудованияПоУчасткамПродолжительность"]]
                durations_hours = [(d.hour + d.minute/60) for d in durations]
                includes = row["ПоказателиОборудованияПоУчасткамВключенДвигатель"]

                # Фактическое время (двигатель включен)
                T_f += sum([dur for dur, inc in zip(durations_hours, includes) if inc])

            K_kf = T_f / 24 if 24 > 0 else 0  # по суткам

            kkf_results.append({
                "Оборудование": equip,
                "Дата": date,
                "Календарный фонд (Тк), ч": 24,
                "Фактическое время работы (Тф), ч": round(T_f, 2),
                "Коэф. использования календарного фонда (Ккф)": round(K_kf, 3),
            })

        # --- Кисвр: считаем отдельно по каждой смене и дате ---
        for (equip, shift, date), group in filtered_df.groupby(["Оборудование", "Смена", filtered_df["Дата"].dt.date]):
            T_sm = 0
            T_sm_f = 0

            for _, row in group.iterrows():
                durations = [datetime.fromisoformat(x) for x in row["ПоказателиОборудованияПоУчасткамПродолжительность"]]
                durations_hours = [(d.hour + d.minute/60) for d in durations]
                includes = row["ПоказателиОборудованияПоУчасткамВключенДвигатель"]

                T_sm += sum(durations_hours)
                T_sm_f += sum([dur for dur, inc in zip(durations_hours, includes) if inc])

            K_is_vr = T_sm_f / T_sm if T_sm > 0 else 0

            kisvr_results.append({
                "Оборудование": equip,
                "Смена": shift,
                "Дата": date,
                "Суммарное время (Тсм), ч": round(T_sm, 2),
                "Рабочее время в смене (Тсмф), ч": round(T_sm_f, 2),
                "Коэф. использования по времени (Кисвр)": round(K_is_vr, 3),
            })

        kkf_df = pd.DataFrame(kkf_results)
        kisvr_df = pd.DataFrame(kisvr_results)

        # Выводим таблицы
        st.subheader("📊 Таблица: Коэф. использования календарного фонда (Ккф)")
        st.dataframe(kkf_df)

        st.subheader("📊 Таблица: Коэф. использования сменного времени (Кисвр)")
        st.dataframe(kisvr_df)

        # -------------------
        # Визуализация через кнопку
        # -------------------
        if st.button("Построить графики"):
            st.subheader("📈 График: Ккф по дням")
            fig_kkf = px.line(
                kkf_df,
                x="Дата",
                y="Коэф. использования календарного фонда (Ккф)",
                color="Оборудование",
                markers=True,
                title="Динамика Ккф по дням"
            )
            st.plotly_chart(fig_kkf, use_container_width=True)

            st.subheader("📈 График: Кисвр по дням и сменам")
            fig_kisvr = px.line(
                kisvr_df,
                x="Дата",
                y="Коэф. использования по времени (Кисвр)",
                color="Оборудование",
                line_dash="Смена",
                markers=True,
                title="Динамика Кисвр по дням и сменам"
            )
            st.plotly_chart(fig_kisvr, use_container_width=True)

    else:
        st.warning("Нет данных для выбранных фильтров")
