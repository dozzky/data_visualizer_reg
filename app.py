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

        # Ккф + Тпл + Кио + Ктг по дате и оборудованию
        for (equip, date), group in filtered_df.groupby(["Оборудование", filtered_df["Дата"].dt.date]):
            T_f = 0   # фактическое время работы
            T_ppr = 0 # время ППР
            T_pzo = T_ob = T_ln = T_reg = T_rem = 0

            for _, row in group.iterrows():
                durations = [datetime.fromisoformat(x) for x in row["ПоказателиОборудованияПоУчасткамПродолжительность"]]
                durations_hours = [(d.hour + d.minute/60) for d in durations]
                includes = row["ПоказателиОборудованияПоУчасткамВключенДвигатель"]
                usage_types = row["ПоказателиОборудованияПоУчасткамВидИспользованияРабочегоВремени"]

                # Фактическое время (двигатель включен)
                T_f += sum([dur for dur, inc in zip(durations_hours, includes) if inc])

                # ППР
                T_ppr += sum([dur for dur, usage in zip(durations_hours, usage_types) if usage == "ППР"])

                # Для Кио
                T_pzo += sum([dur for dur, usage in zip(durations_hours, usage_types) if usage == "ЕО"])
                T_ob  += sum([dur for dur, usage in zip(durations_hours, usage_types) if usage == "Обед"])
                T_ln  += sum([dur for dur, usage in zip(durations_hours, usage_types) if usage == "Личные надобности"])
                T_reg += sum([dur for dur, usage in zip(durations_hours, usage_types) if usage in ["Выдача путевого листа", "Заправка"]])

                # Для Ктг (ремонтные состояния)
                T_rem += sum([dur for dur, usage in zip(durations_hours, usage_types) if usage in [
                    "Аварийный ремонт оборудования узлов и агрегатов",
                    "Обкатка ДВС",
                    "ТО",
                    "Ремонт",
                    "ППР"
                ]])

            T_kl = 24  # календарный фонд за день
            T_pl = T_kl - T_ppr  # плановый фонд
            K_kf = T_f / T_kl if T_kl > 0 else 0

            # Кио
            denom_ki = T_kl - T_pzo - T_ob - T_ln - T_reg
            K_io = T_f / denom_ki if denom_ki > 0 else 0

            # Ктг
            denom_ktg = T_kl - T_ob - T_ln
            K_tg = (denom_ktg - T_rem) / denom_ktg if denom_ktg > 0 else 0

            kkf_results.append({
                "Оборудование": equip,
                "Дата": date,
                "Календарный фонд (Тк), ч": T_kl,
                "Плановый фонд (Тпл), ч": round(T_pl, 2),
                "Фактическое время работы (Тф), ч": round(T_f, 2),
                "Время ППР (Тппр), ч": round(T_ppr, 2),
                "Коэф. использования календарного фонда (Ккф)": round(K_kf, 3),
                "Коэф. использования рабочего фонда (Кио)": round(K_io, 3),
                "Коэф. технической готовности (Ктг)": round(K_tg, 3),
            })

        # Кисвр + Тчсм по дате, смене и оборудованию
        for (equip, shift, date), group in filtered_df.groupby(["Оборудование", "Смена", filtered_df["Дата"].dt.date]):
            T_sm = 0
            T_sm_f = 0
            T_pzo = T_ob = T_ln = T_reg = 0
            for _, row in group.iterrows():
                durations = [datetime.fromisoformat(x) for x in row["ПоказателиОборудованияПоУчасткамПродолжительность"]]
                durations_hours = [(d.hour + d.minute/60) for d in durations]
                includes = row["ПоказателиОборудованияПоУчасткамВключенДвигатель"]
                usage_types = row["ПоказателиОборудованияПоУчасткамВидИспользованияРабочегоВремени"]

                # Суммарное время в смене
                T_sm += sum(durations_hours)

                # Фактическое время (двигатель включен)
                T_sm_f += sum([dur for dur, inc in zip(durations_hours, includes) if inc])

                # Разбивка по видам времени
                T_pzo += sum([dur for dur, usage in zip(durations_hours, usage_types) if usage == "ЕО"])
                T_ob  += sum([dur for dur, usage in zip(durations_hours, usage_types) if usage == "Обед"])
                T_ln  += sum([dur for dur, usage in zip(durations_hours, usage_types) if usage == "Личные надобности"])
                T_reg += sum([dur for dur, usage in zip(durations_hours, usage_types) if usage in ["Выдача путевого листа", "Заправка"]])

            # Чистое время работы в смену
            T_chsm = T_sm - T_pzo - T_ob - T_ln - T_reg

            K_is_vr = T_sm_f / T_sm if T_sm > 0 else 0
            kisvr_results.append({
                "Оборудование": equip,
                "Смена": shift,
                "Дата": date,
                "Суммарное время (Тсм), ч": round(T_sm, 2),
                "Рабочее время в смене (Тсмф), ч": round(T_sm_f, 2),
                "Чистое время работы в смену (Тчсм), ч": round(T_chsm, 2),
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

        cols_extra = st.columns(5)
        
        # Суммарное время ППР за выбранный период
        total_ppr = round(kkf_df["Время ППР (Тппр), ч"].sum(), 2)
        cols_extra[0].metric("Суммарное время ППР (Тппр)", total_ppr)

        # Среднее значение Тпл
        avg_tpl = round(kkf_df["Плановый фонд (Тпл), ч"].mean(), 2)
        cols_extra[1].metric("Среднее значение Тпл", avg_tpl)

        # Среднее значение Тчсм
        avg_chsm = round(kisvr_df["Чистое время работы в смену (Тчсм), ч"].mean(), 2)
        cols_extra[2].metric("Среднее значение Тчсм", avg_chsm)

        # Среднее значение Кио
        avg_kio = round(kkf_df["Коэф. использования рабочего фонда (Кио)"].mean(), 3)
        cols_extra[3].metric("Среднее значение Кио", avg_kio)

        # Среднее значение Ктг
        avg_ktg = round(kkf_df["Коэф. технической готовности (Ктг)"].mean(), 3)
        cols_extra[4].metric("Среднее значение Ктг", avg_ktg)
        
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
            st.subheader("📈 График: Ккф по дням (среднее)")
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
            st.subheader("📈 График: Тпл (плановый фонд) по дням (среднее)")
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
            st.subheader("📈 График: Кисвр по дням (среднее)")
            st.plotly_chart(fig_avg_kisvr, use_container_width=True)

            # --- График Тчсм по дням ---
            avg_chsm_per_day = kisvr_df.groupby("Дата")["Чистое время работы в смену (Тчсм), ч"].mean().reset_index()
            if smoothing_window > 1:
                avg_chsm_per_day["Сглаженное Тчсм"] = avg_chsm_per_day["Чистое время работы в смену (Тчсм), ч"].rolling(smoothing_window, min_periods=1).mean()
            else:
                avg_chsm_per_day["Сглаженное Тчсм"] = avg_chsm_per_day["Чистое время работы в смену (Тчсм), ч"]

            fig_avg_chsm = px.line(
                avg_chsm_per_day,
                x="Дата",
                y="Сглаженное Тчсм",
                markers=True,
                title=f"Среднее Тчсм по дням (сглаживание: {smoothing_window} дней)",
                labels={"Сглаженное Тчсм": "Среднее Тчсм"}
            )
            st.subheader("📈 График: Тчсм по дням (среднее)")
            st.plotly_chart(fig_avg_chsm, use_container_width=True)

            # --- График Кио по дням ---
            avg_kio_per_day = kkf_df.groupby("Дата")["Коэф. использования рабочего фонда (Кио)"].mean().reset_index()
            if smoothing_window > 1:
                avg_kio_per_day["Сглаженный Кио"] = avg_kio_per_day["Коэф. использования рабочего фонда (Кио)"].rolling(smoothing_window, min_periods=1).mean()
            else:
                avg_kio_per_day["Сглаженный Кио"] = avg_kio_per_day["Коэф. использования рабочего фонда (Кио)"]

            fig_avg_kio = px.line(
                avg_kio_per_day,
                x="Дата",
                y="Сглаженный Кио",
                markers=True,
                title=f"Среднее Кио по дням (сглаживание: {smoothing_window} дней)",
                labels={"Сглаженный Кио": "Кио"}
            )
            st.subheader("📈 График: Кио по дням (среднее)")
            st.plotly_chart(fig_avg_kio, use_container_width=True)

            # --- График Ктг по дням ---
            avg_ktg_per_day = kkf_df.groupby("Дата")["Коэф. технической готовности (Ктг)"].mean().reset_index()
            if smoothing_window > 1:
                avg_ktg_per_day["Сглаженный Ктг"] = avg_ktg_per_day["Коэф. технической готовности (Ктг)"].rolling(smoothing_window, min_periods=1).mean()
            else:
                avg_ktg_per_day["Сглаженный Ктг"] = avg_ktg_per_day["Коэф. технической готовности (Ктг)"]

            fig_avg_ktg = px.line(
                avg_ktg_per_day,
                x="Дата",
                y="Сглаженный Ктг",
                markers=True,
                title=f"Среднее Ктг по дням (сглаживание: {smoothing_window} дней)",
                labels={"Сглаженный Ктг": "Ктг"}
            )
            st.subheader("📈 График: Ктг по дням (среднее)")
            st.plotly_chart(fig_avg_ktg, use_container_width=True)
            
        
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

            st.subheader("📈 График: Тчсм по дням и сменам")
            chsm_plot_df = kisvr_df.copy()
            if smoothing_window > 1:
                chsm_plot_df["Сглаженное Тчсм"] = chsm_plot_df.groupby(["Оборудование", "Смена"])["Чистое время работы в смену (Тчсм), ч"].transform(
                    lambda x: x.rolling(smoothing_window, min_periods=1).mean()
                )
            else:
                chsm_plot_df["Сглаженное Тчсм"] = chsm_plot_df["Чистое время работы в смену (Тчсм), ч"]

            fig_chsm = px.line(
                chsm_plot_df,
                x="Дата",
                y="Сглаженное Тчсм",
                color="Оборудование",
                line_dash="Смена",
                markers=True,
                title=f"Динамика Тчсм по дням и сменам (сглаживание: {smoothing_window} дней)",
                labels={"Сглаженное Тчсм": "Тчсм"}
            )
            st.plotly_chart(fig_chsm, use_container_width=True)

            # --- График Кио ---
            st.subheader("📈 График: Кио по дням и сменам")
            kio_plot_df = kkf_df.copy()
            if smoothing_window > 1:
                kio_plot_df["Сглаженный Кио"] = kio_plot_df.groupby(["Оборудование"])["Коэф. использования рабочего фонда (Кио)"].transform(
                    lambda x: x.rolling(smoothing_window, min_periods=1).mean()
                )
            else:
                kio_plot_df["Сглаженный Кио"] = kio_plot_df["Коэф. использования рабочего фонда (Кио)"]

            fig_kio = px.line(
                kio_plot_df,
                x="Дата",
                y="Сглаженный Кио",
                color="Оборудование",
                markers=True,
                title=f"Динамика Кио по дням и оборудованию (сглаживание: {smoothing_window} дней)",
                labels={"Сглаженный Кио": "Кио"}
            )
            st.plotly_chart(fig_kio, use_container_width=True)

            # --- График Ктг ---
            st.subheader("📈 График: Ктг по дням и сменам")
            ktg_plot_df = kkf_df.copy()
            if smoothing_window > 1:
                ktg_plot_df["Сглаженный Ктг"] = ktg_plot_df.groupby(["Оборудование"])["Коэф. технической готовности (Ктг)"].transform(
                    lambda x: x.rolling(smoothing_window, min_periods=1).mean()
                )
            else:
                ktg_plot_df["Сглаженный Ктг"] = ktg_plot_df["Коэф. технической готовности (Ктг)"]

            fig_ktg = px.line(
                ktg_plot_df,
                x="Дата",
                y="Сглаженный Ктг",
                color="Оборудование",
                markers=True,
                title=f"Динамика Ктг по дням и оборудованию (сглаживание: {smoothing_window} дней)",
                labels={"Сглаженный Ктг": "Ктг"}
            )
            st.plotly_chart(fig_ktg, use_container_width=True)

    else:
        st.warning("Нет данных для выбранных фильтров")
