import streamlit as st
import pandas as pd
import json
from datetime import datetime
import plotly.express as px

st.set_page_config(page_title="Анализ работы оборудования", layout="wide")

st.title("📊 Анализ работы оборудования")

uploaded_file = st.file_uploader("Загрузите JSON файл", type="json")

if uploaded_file:
    data = json.load(uploaded_file)
    
    if isinstance(data, dict):
        df = pd.json_normalize(data)
    elif isinstance(data, list):
        df = pd.json_normalize(data)
    else:
        st.error("Некорректный формат JSON")
        st.stop()
    
    df["Дата"] = pd.to_datetime(df["Дата"], errors="coerce")

    st.sidebar.header("Фильтры")

    min_date = df["Дата"].min().date()
    max_date = df["Дата"].max().date()
    period = st.sidebar.date_input("Период", [min_date, max_date])

    смена = st.sidebar.multiselect("Смена", df["Смена"].unique())
    оборудование = st.sidebar.multiselect("Оборудование", df["Оборудование"].unique())
    топливо = st.sidebar.multiselect("Топливо", df["Топливо"].unique())

    smoothing_window = st.sidebar.slider("Сглаживание (кол-во дней)", 1, 10, 1)

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
    with st.expander("📊 Таблица: Все данные"):
        st.dataframe(filtered_df)
    
    if not filtered_df.empty:
        kkf_results = []
        kisvr_results = []

        # Календарный фонд (одинаков для всех)
        days_count = filtered_df["Дата"].dt.date.nunique()
        T_k = days_count * 24

        # Ккф + Тпл по дате и оборудованию
        for (equip, date), group in filtered_df.groupby(["Оборудование", filtered_df["Дата"].dt.date]):
            T_f = 0   # фактическое время работы
            T_ppr = 0 # время ППР
            for _, row in group.iterrows():
                durations = [datetime.fromisoformat(x) for x in row["ПоказателиОборудованияПоУчасткамПродолжительность"]]
                durations_hours = [(d.hour + d.minute/60) for d in durations]
                includes = row["ПоказателиОборудованияПоУчасткамВключенДвигатель"]
                usage_types = row["ПоказателиОборудованияПоУчасткамВидИспользованияРабочегоВремени"]

                # Фактическое время (двигатель включен)
                T_f += sum([dur for dur, inc in zip(durations_hours, includes) if inc])

                # Время ППР
                T_ppr += sum([dur for dur, usage in zip(durations_hours, usage_types) if usage == "ППР"])

            T_kl = 24  # календарный фонд за 1 день
            T_pl = T_kl - T_ppr  # плановый фонд (без ППР)
            K_kf = T_f / T_kl if T_kl > 0 else 0

            kkf_results.append({
                "Оборудование": equip,
                "Дата": date,
                "Календарный фонд (Тк), ч": T_kl,
                "Плановый фонд (Тпл), ч": round(T_pl, 2),
                "Фактическое время работы (Тф), ч": round(T_f, 2),
                "Время ППР (Тппр), ч": round(T_ppr, 2),
                "Коэф. использования календарного фонда (Ккф)": round(K_kf, 3),
            })

        # Кисвр по дате, смене и оборудованию
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

        with st.expander("📊 Таблица: Ккф по дням"):
            st.dataframe(kkf_df)

        with st.expander("📊 Таблица: Кисвр по дням и сменам"):
            st.dataframe(kisvr_df)

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
            
        cols_avg = st.columns(4)
        
        overall_avg_kkf = round(kkf_df["Коэф. использования календарного фонда (Ккф)"].mean(), 3)
        
        days = (period[1] - period[0]).days + 1
        cols_avg[0].metric("Календарный фонд времени Тк", days*24)
        cols_avg[1].metric("Среднее значение Ккф", overall_avg_kkf)
        
        shifts = ["1 смена (07-19)", "2 смена (19-07)"]
        for i, shift in enumerate(shifts):
            avg_shift = kisvr_df[kisvr_df["Смена"] == shift]["Коэф. использования по времени (Кисвр)"].mean()
            avg_shift = round(avg_shift, 3) if not pd.isna(avg_shift) else 0
            cols_avg[i+2].metric(f"Среднее значение Кисвр по {shift}", avg_shift)

        cols_extra = st.columns(2)
        
        # Суммарное время ППР за выбранный период
        total_ppr = round(kkf_df["Время ППР (Тппр), ч"].sum(), 2)
        cols_extra[0].metric("Суммарное время ППР (Тппр)", total_ppr)

        # Среднее значение Тпл
        avg_tpl = round(kkf_df["Плановый фонд (Тпл), ч"].mean(), 2)
        cols_extra[1].metric("Среднее значение Тпл", avg_tpl)
        
        st.subheader("📅 Вывести графики по дням")
        col_graphs = st.columns(2)
        if col_graphs[0].button("Построить графики (среднее значение)"):
            avg_kkf_per_day = kkf_df.groupby("Дата")["Коэф. использования календарного фонда (Ккф)"].mean().reset_index()
            if smoothing_window > 1:
                avg_kkf_per_day["Сглаженное Ккф"] = avg_kkf_per_day["Коэф. использования календарного фонда (Ккф)"].rolling(smoothing_window, min_periods=1).mean()
            else:
                avg_kkf_per_day["Сглаженное Ккф"] = avg_kkf_per_day["Коэф. использования календарного фонда (Ккф)"]
            
            fig_avg_kkf = px.line(
                avg_kkf_per_day,
                x="Дата",
                y="Сглаженное Ккф",
                markers=True,
                title=f"Среднее Ккф по дням (сглаживание: {smoothing_window} дней)",
                labels={"Сглаженное Ккф": "Среднее Ккф"}
            )
            st.plotly_chart(fig_avg_kkf, use_container_width=True)

            # --- График Тпл по дням ---
            avg_tpl_per_day = kkf_df.groupby("Дата")["Плановый фонд (Тпл), ч"].mean().reset_index()
            if smoothing_window > 1:
                avg_tpl_per_day["Сглаженное Тпл"] = avg_tpl_per_day["Плановый фонд (Тпл), ч"].rolling(smoothing_window, min_periods=1).mean()
            else:
                avg_tpl_per_day["Сглаженное Тпл"] = avg_tpl_per_day["Плановый фонд (Тпл), ч"]

            fig_avg_tpl = px.line(
                avg_tpl_per_day,
                x="Дата",
                y="Сглаженное Тпл",
                markers=True,
                title=f"Среднее Тпл по дням (сглаживание: {smoothing_window} дней)",
                labels={"Сглаженное Тпл": "Среднее Тпл"}
            )
            st.plotly_chart(fig_avg_tpl, use_container_width=True)

            avg_kisvr_per_day_shift = kisvr_df.groupby(["Дата", "Смена"])["Коэф. использования по времени (Кисвр)"].mean().reset_index()
            if smoothing_window > 1:
                avg_kisvr_per_day_shift["Сглаженное Кисвр"] = avg_kisvr_per_day_shift.groupby("Смена")["Коэф. использования по времени (Кисвр)"].transform(lambda x: x.rolling(smoothing_window, min_periods=1).mean())
            else:
                avg_kisvr_per_day_shift["Сглаженное Кисвр"] = avg_kisvr_per_day_shift["Коэф. использования по времени (Кисвр)"]
            
            fig_avg_kisvr = px.line(
                avg_kisvr_per_day_shift,
                x="Дата",
                y="Сглаженное Кисвр",
                color="Смена",
                markers=True,
                title=f"Среднее Кисвр по дням и сменам (сглаживание: {smoothing_window} дней)",
                labels={"Сглаженное Кисвр": "Среднее Кисвр"}
            )
            st.plotly_chart(fig_avg_kisvr, use_container_width=True)
        
        if col_graphs[1].button("Построить графики по оборудованию"):
            st.subheader("📈 График: Ккф по дням")
            kkf_plot_df = kkf_df.copy()
            if smoothing_window > 1:
                kkf_plot_df["Сглаженное Ккф"] = kkf_plot_df.groupby("Оборудование")["Коэф. использования календарного фонда (Ккф)"].transform(lambda x: x.rolling(smoothing_window, min_periods=1).mean())
            else:
                kkf_plot_df["Сглаженное Ккф"] = kkf_plot_df["Коэф. использования календарного фонда (Ккф)"]

            fig_kkf = px.line(
                kkf_plot_df,
                x="Дата",
                y="Сглаженное Ккф",
                color="Оборудование",
                markers=True,
                title=f"Динамика Ккф по дням (сглаживание: {smoothing_window} дней)"
            )
            st.plotly_chart(fig_kkf, use_container_width=True)

            st.subheader("📈 График: Тпл (плановый фонд) по дням и оборудованию")
            tpl_plot_df = kkf_df.copy()
            if smoothing_window > 1:
                tpl_plot_df["Сглаженное Тпл"] = tpl_plot_df.groupby("Оборудование")["Плановый фонд (Тпл), ч"].transform(
                    lambda x: x.rolling(smoothing_window, min_periods=1).mean()
                )
            else:
                tpl_plot_df["Сглаженное Тпл"] = tpl_plot_df["Плановый фонд (Тпл), ч"]

            fig_tpl = px.line(
                tpl_plot_df,
                x="Дата",
                y="Сглаженное Тпл",
                color="Оборудование",
                markers=True,
                title=f"Динамика Тпл по дням (сглаживание: {smoothing_window} дней)",
                labels={"Сглаженное Тпл": "Тпл"}
            )
            st.plotly_chart(fig_tpl, use_container_width=True)

            st.subheader("📈 График: Кисвр по дням и сменам")
            kisvr_plot_df = kisvr_df.copy()
            if smoothing_window > 1:
                kisvr_plot_df["Сглаженное Кисвр"] = kisvr_plot_df.groupby(["Оборудование", "Смена"])["Коэф. использования по времени (Кисвр)"].transform(lambda x: x.rolling(smoothing_window, min_periods=1).mean())
            else:
                kisvr_plot_df["Сглаженное Кисвр"] = kisvr_plot_df["Коэф. использования по времени (Кисвр)"]

            fig_kisvr = px.line(
                kisvr_plot_df,
                x="Дата",
                y="Сглаженное Кисвр",
                color="Оборудование",
                line_dash="Смена",
                markers=True,
                title=f"Динамика Кисвр по дням и сменам (сглаживание: {smoothing_window} дней)"
            )
            st.plotly_chart(fig_kisvr, use_container_width=True)

    else:
        st.warning("Нет данных для выбранных фильтров")
