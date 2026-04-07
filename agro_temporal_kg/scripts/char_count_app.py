import streamlit as st
import re
import math

st.set_page_config(page_title="Text File Analyzer")

st.title("📊 Text File Analyzer")

uploaded_file = st.file_uploader(
    "Upload a .txt file",
    type=["txt"]
)

CHUNK_SIZE = 1000
OVERLAP = 150
STEP_SIZE = CHUNK_SIZE - OVERLAP


def analyze_file_in_chunks(file, chunk_size=1024 * 1024):
    chars_with_ws = 0
    chars_without_ws = 0
    word_count = 0
    leftover = ""

    while True:
        chunk = file.read(chunk_size)
        if not chunk:
            break

        text = leftover + chunk.decode("utf-8", errors="ignore")

        chars_with_ws += len(text)
        chars_without_ws += len(re.sub(r"\s+", "", text))
        words = re.findall(r"\b\w+\b", text)
        word_count += len(words)

        match = re.search(r"(\w+)$", text)
        leftover = match.group(1) if match else ""

    return chars_with_ws, chars_without_ws, word_count


if uploaded_file is not None:
    st.info("Analyzing file… this may take a moment for large files ⏳")

    uploaded_file.seek(0)

    chars_ws, chars_no_ws, words = analyze_file_in_chunks(uploaded_file)

    # Chunk calculation
    num_chunks = math.ceil(chars_ws / STEP_SIZE)

    st.success("Analysis complete ✅")

    col1, col2, col3 = st.columns(3)
    col1.metric("Characters (with whitespace)", f"{chars_ws:,}")
    col2.metric("Characters (no whitespace)", f"{chars_no_ws:,}")
    col3.metric("Words", f"{words:,}")

    st.divider()

    st.subheader("🧩 Chunk Calculation")
    st.write(
        f"""
        **Chunk size:** {CHUNK_SIZE} characters  
        **Overlap:** {OVERLAP} characters  
        **Step size:** {STEP_SIZE} characters  

        **Total chunks needed:** **{num_chunks:,}**
        """
    )
