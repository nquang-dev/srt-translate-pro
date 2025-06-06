import streamlit as st
import pysrt
from googletrans import Translator
import io
import os
import time
import re
from datetime import datetime

def split_text_into_chunks(text, max_length=4000):
    """Chia text thành các chunk nhỏ hơn max_length"""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk + sentence) <= max_length:
            current_chunk += sentence + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def translate_text_with_retry(translator, text, target_language='vi', max_retries=3):
    """Dịch text với retry mechanism"""
    for attempt in range(max_retries):
        try:
            result = translator.translate(text, dest=target_language)
            return result.text
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                st.warning(f"Lỗi dịch (thử lại sau {wait_time}s): {str(e)}")
                time.sleep(wait_time)
            else:
                st.error(f"Không thể dịch sau {max_retries} lần thử: {str(e)}")
                return text

def srt_to_string(subs):
    """Chuyển đổi pysrt SubRipFile thành string đúng định dạng SRT"""
    result = []
    for i, sub in enumerate(subs, 1):
        # Format: số thứ tự
        result.append(str(i))
        
        # Format: thời gian
        start_time = sub.start.to_time()
        end_time = sub.end.to_time()
        
        # Chuyển đổi thời gian sang định dạng SRT (HH:MM:SS,mmm)
        start_str = f"{start_time.hour:02d}:{start_time.minute:02d}:{start_time.second:02d},{start_time.microsecond//1000:03d}"
        end_str = f"{end_time.hour:02d}:{end_time.minute:02d}:{end_time.second:02d},{end_time.microsecond//1000:03d}"
        
        result.append(f"{start_str} --> {end_str}")
        
        # Nội dung phụ đề
        result.append(sub.text)
        
        # Dòng trống giữa các phụ đề
        result.append("")
    
    return "\n".join(result)

def translate_srt_content_advanced(srt_content, target_language='vi'):
    """Dịch nội dung file SRT với xử lý file dài"""
    translator = Translator()
    
    # Parse SRT content
    subs = pysrt.from_string(srt_content)
    total_subs = len(subs)
    
    st.info(f"🔄 Bắt đầu dịch {total_subs} dòng phụ đề...")
    
    # Tạo progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Dịch từng dòng
    batch_size = 10
    
    for i, sub in enumerate(subs):
        try:
            # Cập nhật status
            status_text.text(f"Đang dịch dòng {i+1}/{total_subs}: {sub.text[:50]}...")
            
            # Dịch text nếu có nội dung
            if sub.text.strip():
                translated_text = translate_text_with_retry(translator, sub.text, target_language)
                sub.text = translated_text
            
            # Cập nhật progress
            progress_bar.progress((i + 1) / total_subs)
            
            # Nghỉ sau mỗi batch
            if (i + 1) % batch_size == 0:
                time.sleep(1)
                
        except Exception as e:
            st.warning(f"Lỗi dòng {i+1}: {str(e)}")
            continue
    
    status_text.text("✅ Hoàn thành dịch!")
    
    # Chuyển đổi về string SRT đúng định dạng
    return srt_to_string(subs)

def translate_srt_content_batch(srt_content, target_language='vi'):
    """Dịch nội dung file SRT theo batch"""
    translator = Translator()
    
    # Parse SRT content
    subs = pysrt.from_string(srt_content)
    total_subs = len(subs)
    
    st.info(f"🚀 Dịch nhanh {total_subs} dòng phụ đề (batch mode)...")
    
    # Gộp text để dịch batch
    texts_to_translate = []
    text_mapping = {}
    
    for i, sub in enumerate(subs):
        if sub.text.strip():
            texts_to_translate.append(sub.text)
            text_mapping[sub.text] = i
    
    # Chia thành chunks
    batch_size = 20
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    translated_texts = {}
    
    for i in range(0, len(texts_to_translate), batch_size):
        batch = texts_to_translate[i:i+batch_size]
        batch_text = "\n###SEPARATOR###\n".join(batch)
        
        try:
            status_text.text(f"Đang dịch batch {i//batch_size + 1}/{(len(texts_to_translate)-1)//batch_size + 1}...")
            
            if len(batch_text) > 4000:
                # Dịch từng cái nếu quá dài
                for text in batch:
                    translated = translate_text_with_retry(translator, text, target_language)
                    translated_texts[text] = translated
                    time.sleep(0.5)
            else:
                # Dịch cả batch
                translated_batch = translate_text_with_retry(translator, batch_text, target_language)
                translated_list = translated_batch.split("###SEPARATOR###")
                
                for original, translated in zip(batch, translated_list):
                    translated_texts[original] = translated.strip()
            
            progress_bar.progress((i + batch_size) / len(texts_to_translate))
            time.sleep(1)
            
        except Exception as e:
            st.warning(f"Lỗi batch {i//batch_size + 1}: {str(e)}")
            # Fallback: dịch từng cái
            for text in batch:
                translated = translate_text_with_retry(translator, text, target_language)
                translated_texts[text] = translated
                time.sleep(0.5)
    
    # Áp dụng bản dịch vào subs
    for sub in subs:
        if sub.text.strip() and sub.text in translated_texts:
            sub.text = translated_texts[sub.text]
    
    status_text.text("✅ Hoàn thành dịch batch!")
    
    # Chuyển đổi về string SRT đúng định dạng
    return srt_to_string(subs)

def display_srt_preview(srt_content):
    """Hiển thị preview của file SRT"""
    try:
        # Parse từ string SRT
        subs = pysrt.from_string(srt_content)
        
        st.subheader("📺 Xem trước bản dịch:")
        
        # Thống kê
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Tổng số dòng", len(subs))
        with col2:
            if subs:
                total_duration = subs[-1].end - subs[0].start
                st.metric("Thời lượng", f"{total_duration}")
            else:
                st.metric("Thời lượng", "N/A")
        with col3:
            total_chars = sum(len(sub.text) for sub in subs)
            st.metric("Tổng ký tự", f"{total_chars:,}")
        
        # Preview với search
        search_term = st.text_input("🔍 Tìm kiếm trong phụ đề:")
        
        # Filter subs based on search
        if search_term:
            filtered_subs = [sub for sub in subs if search_term.lower() in sub.text.lower()]
            st.info(f"Tìm thấy {len(filtered_subs)} kết quả")
            display_subs = filtered_subs
        else:
            display_subs = subs[:30]  # Hiển thị 30 dòng đầu
            if len(subs) > 30:
                st.info(f"Hiển thị 30/{len(subs)} dòng đầu tiên. Sử dụng tìm kiếm để xem các dòng khác.")
        
        # Display subtitles
        for i, sub in enumerate(display_subs):
            original_index = subs.index(sub) + 1 if sub in subs else i + 1
            
            with st.expander(f"Dòng {original_index}: {sub.start} --> {sub.end}"):
                st.write(sub.text)
                if search_term and search_term.lower() in sub.text.lower():
                    st.markdown(f"**🔍 Từ khóa tìm thấy:** {search_term}")
        
    except Exception as e:
        st.error(f"❌ Lỗi khi hiển thị preview: {str(e)}")
        st.write("**Raw content (first 1000 chars):**")
        st.text(srt_content[:1000])

def main():
    st.set_page_config(
        page_title="SRT Translator Pro",
        page_icon="🌐",
        layout="wide"
    )
    
    st.title("🌐 SRT Translator Pro - Hỗ trợ file dài")
    st.markdown("---")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Cài đặt")
        
        # Chọn phương pháp dịch
        translation_method = st.radio(
            "Phương pháp dịch:",
            ["An toàn (từng dòng)", "Nhanh (batch)"],
            help="An toàn: chậm hơn nhưng ít lỗi. Nhanh: nhanh hơn nhưng có thể bị lỗi với file rất dài"
        )
        
        st.markdown("---")
        st.header("ℹ️ Thông tin")
        st.write("• Hỗ trợ file SRT **không giới hạn độ dài**")
        st.write("• Xử lý thông minh cho file > 5000 ký tự")
        st.write("• Retry tự động khi lỗi")
        st.write("• Progress tracking chi tiết")
        
        st.markdown("---")
        st.write("**Hỗ trợ:** .srt files")
        st.write("**Dịch từ:** Auto-detect")
        st.write("**Dịch sang:** Tiếng Việt")
    
    # File uploader
    uploaded_file = st.file_uploader(
        "📁 Chọn file SRT cần dịch:",
        type=['srt'],
        help="Hỗ trợ file SRT không giới hạn kích thước"
    )
    
    if uploaded_file is not None:
        try:
            # Đọc file với encoding detection
            try:
                srt_content = uploaded_file.read().decode('utf-8')
            except UnicodeDecodeError:
                try:
                    uploaded_file.seek(0)
                    srt_content = uploaded_file.read().decode('utf-8-sig')
                except:
                    uploaded_file.seek(0)
                    srt_content = uploaded_file.read().decode('latin-1')
            
            # Thông tin file
            file_size = len(srt_content)
            subs = pysrt.from_string(srt_content)
            
            # Hiển thị thông tin chi tiết
            st.success(f"✅ Đã tải file: **{uploaded_file.name}**")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Số dòng phụ đề", len(subs))
            with col2:
                st.metric("Kích thước file", f"{file_size:,} ký tự")
            with col3:
                if subs:
                    duration = subs[-1].end - subs[0].start
                    st.metric("Thời lượng", str(duration))
                else:
                    st.metric("Thời lượng", "N/A")
            with col4:
                avg_chars = file_size // len(subs) if subs else 0
                st.metric("TB ký tự/dòng", avg_chars)
            
            # Cảnh báo cho file dài
            if file_size > 10000:
                st.warning("⚠️ File khá dài. Quá trình dịch có thể mất vài phút. Hãy kiên nhẫn!")
            
            # Nút dịch
            if st.button("🚀 Bắt đầu dịch", type="primary"):
                start_time = time.time()
                
                with st.spinner("🔄 Đang dịch file... Vui lòng không tắt trang..."):
                    try:
                        # Chọn phương pháp dịch
                        if translation_method == "An toàn (từng dòng)":
                            translated_content = translate_srt_content_advanced(srt_content)
                        else:
                            translated_content = translate_srt_content_batch(srt_content)
                        
                        # Lưu kết quả
                        st.session_state.translated_content = translated_content
                        st.session_state.original_filename = uploaded_file.name
                        
                        end_time = time.time()
                        duration = end_time - start_time
                        
                        st.success(f"🎉 Dịch hoàn thành trong {duration:.1f} giây!")
                        
                        # Hiển thị sample để kiểm tra
                        st.subheader("📋 Mẫu kết quả:")
                        sample_lines = translated_content.split('\n')[:10]
                        st.text('\n'.join(sample_lines))
                        
                    except Exception as e:
                        st.error(f"❌ Lỗi khi dịch: {str(e)}")
                        st.info("💡 Thử chuyển sang phương pháp 'An toàn' nếu gặp lỗi")
            
            # Hiển thị tùy chọn sau khi dịch
            if 'translated_content' in st.session_state and st.session_state.get('original_filename') == uploaded_file.name:
                st.markdown("---")
                st.subheader("🎯 Lựa chọn của bạn:")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("👁️ Xem trước online", use_container_width=True):
                        st.session_state.show_preview = True
                
                with col2:
                    # Tạo tên file
                    original_name = st.session_state.original_filename
                    name_without_ext = os.path.splitext(original_name)[0]
                    new_filename = f"{name_without_ext}_vietnamese.srt"
                    
                    st.download_button(
                        label="💾 Tải xuống file đã dịch",
                        data=st.session_state.translated_content,
                        file_name=new_filename,
                        mime="text/plain",
                        use_container_width=True
                    )
                
                # Hiển thị preview nếu được yêu cầu
                if st.session_state.get('show_preview', False):
                    display_srt_preview(st.session_state.translated_content)
                
        except Exception as e:
            st.error(f"❌ Lỗi khi xử lý file: {str(e)}")
            st.write("**Debug info:**")
            st.write(f"File name: {uploaded_file.name}")
            st.write(f"File size: {uploaded_file.size} bytes")
    
    else:
        st.info("👆 Vui lòng chọn file SRT để bắt đầu")
        
        # Reset session state khi không có file
        if 'translated_content' in st.session_state:
            del st.session_state.translated_content
        if 'show_preview' in st.session_state:
            del st.session_state.show_preview
        
        # Hướng dẫn
        with st.expander("📚 Hướng dẫn sử dụng"):
            st.markdown("""
            ### 🔧 Cách sử dụng:
            
            1. **Upload file SRT** tiếng Anh
            2. **Chọn phương pháp dịch** phù hợp
            3. **Nhấn "Bắt đầu dịch"** và chờ đợi
            4. **Xem trước** hoặc **tải xuống** kết quả
            
            ### ⚙️ Phương pháp dịch:
            - **An toàn:** Dịch từng dòng, chậm nhưng ít lỗi
            - **Nhanh:** Dịch theo batch, nhanh hơn
            
            ### 💡 Lưu ý:
            - File càng dài càng mất nhiều thời gian
            - Không tắt trang trong khi dịch
            - Kiểm tra kết quả trước khi sử dụng
            """)

if __name__ == "__main__":
    main()
