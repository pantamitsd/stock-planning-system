import streamlit as st
import re
import pandas as pd
from itertools import combinations

st.title("📦 Stock Planning System for Retail (Note= Only Act_B2B, Retail Warhouse Stock)")

# -----------------------------
# GOOGLE SHEET CSV URL
# -----------------------------
SHEET_ID = "1bJWEG8F1mg-5vIRKs0annYZvArh4koErzXLomVFfKyY"
GID = "0"

url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

@st.cache_data
def load_data():
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip()
    return df

df = load_data()

st.write("Total rows loaded:", len(df))

color_map = {
"BLK": ["black", "blk","Black"],
"NVY": ["navy"],
"OLVBRN": ["olive brown", "olive","olive/brown"],
"BEGBRN": ["begbrown", "beige brown"],
"BEG": ["beige"],
"GRY": ["grey", "gray"],
"SKY": ["sky", "skyblue", "sky blue"],
"MAR": ["maroon"],
"CHA": ["charcoal"]
}

df["farukhnagar_stock"]= df["ACT_B2B"]+ df["RETAIL"]
df["Free Stock"]= df["L1 FREE STOCK"]

blocking_cols = ["ONLINE", "RETAIL BLOCKING", "NORTH", "EAST", "WEST", "SOUTH"]

for col in blocking_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

# ======================================================
# 🔧 SET PATTERN FUNCTION
# ======================================================
def get_model_count(sku):

    sku_lower = sku.lower()

    parts = sku_lower.split("_")

    model_part = parts[1]

    # comma model format
    if "," in model_part:
        return len(model_part.split(","))

    # underscore model format
    else:
        models = []
        for p in parts[1:]:
            if p.isdigit() or p.startswith("htl"):
                models.append(p)
            else:
                break

        return len(models)




def find_best_sku(order_text, df):

    order_text = str(order_text).lower()
    order_text = order_text.replace("/", " ")
    is_set = "set" in order_text

    for _, row in df.iterrows():

        sku = row["New SKU Code"]
        sku_lower = sku.lower()

        brand = sku_lower.split("_")[0]

        if brand not in order_text:
            continue

        for code, names in color_map.items():

            if code.lower() in sku_lower:

                for name in names:

                    if name in order_text:

                        # check set of 3
                        if is_set:

                            model_count = get_model_count(sku_lower)

                            if model_count != 3:
                                continue

                        return sku

    return order_text



def calculate_set_from_pattern(df, pattern, order_qty):
    try:
        parts = pattern.split("_")

        if len(parts) < 4:
            return {"error": "Invalid pattern structure."}

        brand = parts[0]

        # Detect comma-style OR underscore-style
        if "," in pattern:
            # Format: BRAND_HTLxxx,yyy,zzz_COLOR_size,size,sizeCM
            model_part = parts[1]
            color = parts[2]
            size_part = parts[3]

            models = model_part.replace("HTL", "").split(",")
            sizes = size_part.replace("CM", "").split(",")

        else:
            # Format: BRAND_HTLxxx_yyy_zzz_COLOR_size_size_sizeCM
            brand = parts[0]
            size_parts = parts[-3:]
            color = parts[-4]
            model_parts = parts[1:-4]

            models = []
            for mp in model_parts:
                models.append(mp.replace("HTL", "").replace("ST", ""))

            sizes = [s.replace("CM", "") for s in size_parts]

        if len(models) != len(sizes):
            return {"error": "Model count and size count mismatch."}

        generated_skus = []
        for model, size in zip(models, sizes):
            prefix = re.match(r"[A-Za-z]+", parts[1]).group()  # HTL or ST
            sku = f"{brand}_{prefix}{model}_{color}_{size}CM"
            generated_skus.append(sku)

        two_set_skus = []

        for combo in combinations(list(zip(models, sizes)), 2):
            m1, s1 = combo[0]
            m2, s2 = combo[1]

            set2_sku = f"{brand}_HTL{m1},{m2}_{color}_{s1},{s2}CM"

            two_set_skus.append(set2_sku)

        # third single SKU
        single_skus = generated_skus

        two_set_results = {}

        for set2 in two_set_skus:

            set2_row = df[df["New SKU Code"] == set2]

            if not set2_row.empty:

                set2_stock = int(set2_row.iloc[0]["farukhnagar_stock"])

                # third sku detect
                for single in single_skus:

                    if single.split("_")[1].replace("HTL", "") not in set2:

                        single_row = df[df["New SKU Code"] == single]

                        if not single_row.empty:
                            single_stock = int(single_row.iloc[0]["farukhnagar_stock"])

                            possible_sets = min(set2_stock, single_stock)

                            two_set_results[(set2, single)] = possible_sets

        group_df = df[df["New SKU Code"].isin(generated_skus)]

        if group_df.empty:
            return {"error": "No matching SKUs found in sheet."}

        group_df["PHYSICAL_STOCK"] = pd.to_numeric(
            group_df["farukhnagar_stock"], errors="coerce"
        ).fillna(0)

        stocks = group_df["PHYSICAL_STOCK"].tolist()
        max_sets = min(stocks)

        model_stock = {}

        for _, row in group_df.iterrows():
            model_stock[row["New SKU Code"]] = int(row["PHYSICAL_STOCK"])



        breakdown = {}

        for _, row in group_df.iterrows():

            block_info = []

            for col in blocking_cols:
                if col in row and row[col] > 0:
                    block_info.append(f"{col}({int(row[col])})")

            breakdown[row["New SKU Code"]] = {
                "available": int(row["PHYSICAL_STOCK"]),
                "blocking": ", ".join(block_info) if block_info else "No Blocking"
            }

        return {
            "generated_skus": generated_skus,
            "max_sets": int(max_sets),
            "shortage": max(0, order_qty - max_sets),
            "breakdown": breakdown,
            "two_set_results": two_set_results
        }

    except Exception as e:
        return {"error": f"Format Error: {str(e)}"}


def check_single_break_sets(df, single_sku, order_qty):

    parts = single_sku.split("_")
    brand = parts[0]
    model = parts[1].replace("HTL","")
    color = parts[2]
    size = parts[3]

    total_available = 0
    breakdown = []

    # 🔎 find sets containing this model
    possible_sets = df[
        (df["New SKU Code"].str.contains(f"HTL{model}")) &
        (df["New SKU Code"].str.contains(color))
        ]

    for _, row in possible_sets.iterrows():

        sku = row["New SKU Code"]

        # skip same single sku
        if sku == single_sku:
            continue

        if "," in sku:  # set sku

            stock = int(row["farukhnagar_stock"])

            if stock > 0:

                total_available += stock

                breakdown.append(
                    f"{sku} → {stock} pcs can break"
                )

    return {
        "total": total_available,
        "details": breakdown
    }



# -----------------------------
# CHECK REQUIRED COLUMN
# -----------------------------
if "New SKU Code" not in df.columns:
    st.error("❌ Column 'New SKU Code' not found — check your sheet!")
else:

    # ======================================================
    # 🔽 SINGLE SKU VIEW
    # ======================================================

    sku_list = df["New SKU Code"].dropna().unique()
    selected_sku = st.selectbox("Select SKU", sku_list)

    sku_data = df[df["New SKU Code"] == selected_sku]

    if not sku_data.empty:
        row = sku_data.iloc[0]

        st.subheader("📊 Stock Details")
        col1, col2, col3 = st.columns(3)
        col1.metric("ACT B2B", row.get("ACT_B2B", 0))
        col2.metric("Retail", row.get("RETAIL", 0))
        col3.metric("Mumbai EMI ZA", row.get("MUMBAI_EMIZA", 0))

    # ======================================================
    # 📋 FULL TABLE - RETAIL L1 VIEW
    # ======================================================

    st.markdown("---")
    st.subheader("📋 Retail L1 Stock Table (All SKUs)")

    # Safe numeric conversion
    df["ACT_B2B"] = pd.to_numeric(df["ACT_B2B"], errors="coerce").fillna(0)
    df["RETAIL"] = pd.to_numeric(df["RETAIL"], errors="coerce").fillna(0)
    df["RETAIL BLOCKING"] = pd.to_numeric(df["RETAIL BLOCKING"], errors="coerce").fillna(0)

    # L1 total
    df["L1_TOTAL_RETAIL"] = df["ACT_B2B"] + df["RETAIL"]

    # L1 Stock Available
    df["L1_STOCK_AVAILABLE"] = df[["L1_TOTAL_RETAIL", "RETAIL BLOCKING"]].min(axis=1)

    final_table = df[[
        "New SKU Code",
        "STATUS",
        "Category",
        "L1_TOTAL_RETAIL",
        "RETAIL BLOCKING",
        "L1_STOCK_AVAILABLE"
    ]]

    final_table = final_table.sort_values(by="L1_STOCK_AVAILABLE", ascending=True)

    st.dataframe(final_table, use_container_width=True)

    # ======================================================
    # 🧩 SET AVAILABILITY ENGINE
    # ======================================================

    st.markdown("---")
    st.subheader("🧩 Check Set Availability")

    set_sku_input = st.text_input(
        "Enter Set Pattern (Example: HORIZON_HTL122,123,124_BLK_55,65,75CM)"
    )

    order_qty = st.number_input("Enter Order Quantity (Sets)", min_value=1, step=1)

    if set_sku_input:

        result = calculate_set_from_pattern(df, set_sku_input, order_qty)

        direct_match = df[df["New SKU Code"] == set_sku_input]

        if not direct_match.empty:
            direct_stock = pd.to_numeric(
                direct_match.iloc[0]["farukhnagar_stock"],
                errors="coerce"
            )
            direct_stock = 0 if pd.isna(direct_stock) else int(direct_stock)

            st.write("### Full Set Direct Stock (Farukhnagar):")
            st.write(direct_stock)

        if "error" in result:
            st.error(result["error"])
        else:
            st.write("### Generated SKUs:")
            for sku in result["generated_skus"]:
                st.write(sku)

            # 🔹 Pehle stock breakdown dikhao
            st.write("### Individual SKU Stock:")

            for sku, info in result["breakdown"].items():
                st.write(
                    f"{sku} → Available: {info['available']} | Blocked By: {info['blocking']}"
                )

            # 🔹 Fir 3-set result dikhao
            st.write("### 3-Set Possible:")
            st.write(result["max_sets"])

            # 🔹 Fir 2-set combinations
            st.write("### 2-Set Combinations:")

            for combo, qty in result["two_set_results"].items():
                set2 = combo[0]
                single = combo[1]

                model_pair = set2.split("_")[1]
                model_single = single.split("_")[1].replace("HTL", "")

                st.write(f"{model_pair}+{model_single} → {qty} sets")

            # 🔹 Shortage last me
            if order_qty > result["max_sets"]:
                st.warning(f"⚠ Shortage: {result['shortage']} sets")
            else:
                st.success("✅ Full Order Possible")

    st.markdown("---")
    st.subheader("📂 Bulk Order Upload Checker")

    uploaded_file = st.file_uploader(
        "Upload Order File (CSV or Excel)",
        type=["csv", "xlsx"]
    )

    if uploaded_file:

        if uploaded_file.name.endswith(".csv"):
            order_df = pd.read_csv(uploaded_file)
        else:
            order_df = pd.read_excel(uploaded_file)

        st.write("Uploaded Orders:")
        st.dataframe(order_df)

        results = []

        for _, row in order_df.iterrows():

            pattern = row["SKU"]
            qty = int(row["Order Qty"])

            options = []

            result = {}

            if "," in pattern:
                result = calculate_set_from_pattern(df, pattern, qty)

            direct_match = df[df["New SKU Code"] == pattern]
            online_block = 0
            retail_block = 0

            if not direct_match.empty:
                online_block = pd.to_numeric(
                    direct_match.iloc[0].get("ONLINE", 0),
                    errors="coerce"
                )

                retail_block = pd.to_numeric(
                    direct_match.iloc[0].get("RETAIL BLOCKING", 0),
                    errors="coerce"
                )

                online_block = 0 if pd.isna(online_block) else int(online_block)
                retail_block = 0 if pd.isna(retail_block) else int(retail_block)

            if not direct_match.empty:
                stock = pd.to_numeric(
                    direct_match.iloc[0]["farukhnagar_stock"],
                    errors="coerce"
                )
                stock = 0 if pd.isna(stock) else int(stock)
            else:
                stock = result.get("max_sets", 0)

            # ⭐ SINGLE BREAK LOGIC
            if "," not in pattern:

                single_break = check_single_break_sets(df, pattern, qty)

                if single_break["total"] > 0:
                    options.append(
                        "🧩 Build by Breaking Sets\n" +
                        "\n".join(single_break["details"])
                    )




            # 1️⃣ Direct set
            if stock >= qty:
                status = "✅ Available"

            else:

                # 2️⃣ Build from Singles
                if result.get("breakdown") and result.get("max_sets", 0):

                    single_parts = []

                    for sku, info in result["breakdown"].items():
                        model = sku.split("_")[1].replace("HTL", "")
                        row_match = df[df["New SKU Code"] == sku]

                        online = int(row_match.iloc[0].get("ONLINE", 0))
                        retail = int(row_match.iloc[0].get("RETAIL BLOCKING", 0))
                        north = int(row_match.iloc[0].get("NORTH", 0))
                        east = int(row_match.iloc[0].get("EAST", 0))
                        west = int(row_match.iloc[0].get("WEST", 0))
                        south = int(row_match.iloc[0].get("SOUTH", 0))
                        free = int(row_match.iloc[0].get("Free Stock", 0))

                        single_parts.append(
                            f"{model} → Stock {info['available']} | Online {online} | Retail {retail} | "
                            f"North {north} | East {east} | West {west} | South {south} | Free {free}"
                        )

                    options.append(
                        "🧩 Build from Singles\n" + "\n".join(single_parts)
                    )

                # 3️⃣ Build using 2-set combos
                if result.get("two_set_results"):

                    combo_parts = []

                    for combo, qty_possible in result["two_set_results"].items():
                        set2, single = combo

                            # rows fetch
                        row1 = df[df["New SKU Code"] == set2].iloc[0]
                        row2 = df[df["New SKU Code"] == single].iloc[0]

                            # model names
                        model_pair = set2.split("_")[1]  # 127,128
                        model_single = single.split("_")[1].replace("HTL", "")  # 129

                        combo_parts.append(
                            f"{model_pair}+{model_single} → {qty_possible} sets\n"
                            f"{model_pair} → Online {int(row1['ONLINE'])} | Retail {int(row1['RETAIL BLOCKING'])} | "
                            f"North {int(row1['NORTH'])} | East {int(row1['EAST'])} | West {int(row1['WEST'])} | South {int(row1['SOUTH'])} | Free {int(row1['Free Stock'])}\n"
                            f"{model_single} → Online {int(row2['ONLINE'])} | Retail {int(row2['RETAIL BLOCKING'])} | "
                            f"North {int(row2['NORTH'])} | East {int(row2['EAST'])} | West {int(row2['WEST'])} | South {int(row2['SOUTH'])} | Free {int(row2['Free Stock'])}"
                        )

                    options.append(
                        "🧩 Build using 2-Set\n" + "\n".join(combo_parts)
                    )

                if options:
                    status = "⚠ Set Not Available\n\n" + "\n\n".join(options)
                else:
                    status = "❌ Short"


            free_stock = 0

            if not direct_match.empty:
                free_stock = pd.to_numeric(
                    direct_match.iloc[0].get("Free Stock", 0),
                    errors="coerce"
                )

                free_stock = 0 if pd.isna(free_stock) else int(free_stock)

            results.append({
                "Set SKU": pattern,
                "Order Qty": qty,
                "Available Stock": stock,
                "ONLINE Blocking": online_block,
                "Retail Blocking": retail_block,
                "Free Stock": free_stock,
                "Status": status,
            })

        result_df = pd.DataFrame(results)

        st.subheader("📊 Bulk Order Result")
        st.dataframe(result_df, use_container_width=True)

    st.markdown("---")
    st.subheader("🧠 Smart Text Order Checker")

    order_text = st.text_area("Paste Order Text",
                              placeholder=""" Fatboy black 5pc Fatboy navy 5pc Rome olive brown 10set Rome begbrown 65cm 3pcs """)

    if order_text:
        lines = order_text.strip().split("\n")
        smart_results = []

        for line in lines:
            words = line.lower().split()

            qty = 1
            match = re.search(r'(\d+)\s*(pc|pcs|set|sets)', line, re.IGNORECASE)

            if match:
                qty = int(match.group(1))

            detected_sku = find_best_sku(line, df)

            smart_results.append({
                "Order Text": line,
                "Detected SKU": detected_sku,
                "Qty": qty
            })

        # LOOP KHATAM
        smart_df = pd.DataFrame(smart_results)

        st.subheader("📊 Detected Orders")
        st.dataframe(smart_df)
