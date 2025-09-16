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
    
    # Нормализуем JSON
    if isinstance(data, dict):
        df = pd.json_normalize(data)
    elif isinstance(data, list):
        df = pd.json_normalize(data)
    else:
        st.error("Некорректный формат JSON")
        st.stop()
    
    # Преобразуем дату
    df["Дата"] = pd.to_datetime(df["Дата"], errors="coerce")

    # -------------------
    # Фильтры
    # -------------------
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

    # -------------------
    # Расчеты по оборудованию
    # -------------------

    st.subheader("Отфильтрованные данные")
    with st.expander("📊 Таблица: Все данные"):
        st.dataframe(filtered_df)
    
    if not filtered_df.empty:
        kkf_results = []
        kisvr_results = []

        # Календарный фонд (одинаков для всех)
        days_count = filtered_df["Дата"].dt.date.nunique()
        T_k = days_count * 24

        # --- Ккф по дате и оборудованию ---
        for (equip, date), group in filtered_df.groupby(["Оборудование", filtered_df["Дата"].dt.date]):
            T_f = 0
            for _, row in group.iterrows():
                durations = [datetime.fromisoformat(x) for x in row["ПоказателиОборудованияПоУчасткамПродолжительность"]]
                durations_hours = [(d.hour + d.minute/60) for d in durations]
                includes = row["ПоказателиОборудованияПоУчасткамВключенДвигатель"]
                T_f += sum([dur for dur, inc in zip(durations_hours, includes) if inc])
            K_kf = T_f / 24 if 24 > 0 else 0
            kkf_results.append({
                "Оборудование": equip,
                "Дата": date,
                "Календарный фонд (Тк), ч": 24,
                "Фактическое время работы (Тф), ч": round(T_f, 2),
                "Коэф. использования календарного фонда (Ккф)": round(K_kf, 3),
            })

        # --- Кисвр по дате, смене и оборудованию ---
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

        # -------------------
        # Скрытые таблицы через expander
        # -------------------
        with st.expander("📊 Таблица: Ккф по дням"):
            st.dataframe(kkf_df)

        with st.expander("📊 Таблица: Кисвр по дням и сменам"):
            st.dataframe(kisvr_df)

        # -------------------
        # Средние значения
        # -------------------
        st.subheader("📌 Средние значения за выбранный период")

        # Среднее Ккф по оборудованию
        avg_kkf = kkf_df.groupby("Оборудование")["Коэф. использования календарного фонда (Ккф)"].mean().reset_index()
        avg_kkf.rename(columns={"Коэф. использования календарного фонда (Ккф)": "Среднее Ккф"}, inplace=True)
        with st.expander("Среднее Ккф по оборудованию:"):
            st.dataframe(avg_kkf)

        # Среднее Кисвр по сменам
        avg_kisvr = kisvr_df.groupby(["Оборудование", "Смена"])["Коэф. использования по времени (Кисвр)"].mean().reset_index()
        avg_kisvr.rename(columns={"Коэф. использования по времени (Кисвр)": "Среднее Кисвр"}, inplace=True)
        with st.expander("Среднее Кисвр по сменам:"):
            st.dataframe(avg_kisvr)
            
        cols_avg = st.columns(3)
        
        overall_avg_kkf = round(kkf_df["Коэф. использования календарного фонда (Ккф)"].mean(), 3)
        cols_avg[0].metric("Среднее значение Ккф", overall_avg_kkf)
        
        # Среднее Кисвр по сменам
        shifts = ["1 смена (07-19)", "2 смена (19-07)"]
        for i, shift in enumerate(shifts):
            avg_shift = kisvr_df[kisvr_df["Смена"] == shift]["Коэф. использования по времени (Кисвр)"].mean()
            avg_shift = round(avg_shift, 3) if not pd.isna(avg_shift) else 0
            cols_avg[i+1].metric(f"Среднее значение Кисвр по {shift}", avg_shift)
            
        # -------------------
        # Кнопка для построения графиков
        # -------------------
        if st.button("Построить графики (среднее значение)"):
            avg_kkf_per_day = kkf_df.groupby("Дата")["Коэф. использования календарного фонда (Ккф)"].mean().reset_index()
            fig_avg_kkf = px.line(
                avg_kkf_per_day,
                x="Дата",
                y="Коэф. использования календарного фонда (Ккф)",
                markers=True,
                title="Среднее Ккф по дням за выбранный период",
                labels={"Коэф. использования календарного фонда (Ккф)": "Среднее Ккф"}
            )
            st.plotly_chart(fig_avg_kkf, use_container_width=True)

            avg_kisvr_per_day_shift = kisvr_df.groupby(["Дата", "Смена"])["Коэф. использования по времени (Кисвр)"].mean().reset_index()
            fig_avg_kisvr = px.line(
                avg_kisvr_per_day_shift,
                x="Дата",
                y="Коэф. использования по времени (Кисвр)",
                color="Смена",
                markers=True,
                title="Среднее Кисвр по дням и сменам",
                labels={"Коэф. использования по времени (Кисвр)": "Среднее Кисвр"}
            )
            st.plotly_chart(fig_avg_kisvr, use_container_width=True)
        
        if st.button("Построить графики по оборудованию"):
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
