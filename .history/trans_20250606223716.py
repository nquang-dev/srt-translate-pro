import streamlit as st
import pysrt
from googletrans import Translator
import io
import os
import time
import re
from datetime import datetime
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

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
                time.sleep(wait_time)
            else:
                return text

def srt_to_string(subs):
    """Chuyển đổi pysrt SubRipFile thành string đúng định dạng SRT"""
    result = []
    for i, sub in enumerate(subs, 1):
        result.append(str(i))
        
        start_time = sub.start.to_time()
        end_time = sub.end.to_time()
        
        start_str = f"{start_time.hour:02d}:{start_time.minute:02d}:{start_time.second:02d},{start_time.microsecond//1000:03d}"
        end_str = f"{end_time.hour:02d}:{end_time.minute:02d}:{end_time.second:02d},{end_time.microsecond//1000:03d}"
        
        result.append(f"{start_str} --> {end_str}")
        result.append(sub.text)
        result.append("")
    
    return "\n".join(result)

def translate_single_file(file_content, filename, translation_method, progress_callback=None):
    """Dịch một file SRT"""
    try:
        translator = Translator()
        
        # Parse SRT content
        subs = pysrt.from_string(file_content)
        total_subs = len(subs)
        
        if progress_callback:
            progress_callback(f"🔄 Bắt đầu dịch {filename} ({total_subs} dòng)...")
        
        if translation_method == "An toàn (từng dòng)":
            # Dịch từng dòng
            for i, sub in enumerate(subs):
                if sub.text.strip():
                    translated_text = translate_text_with_retry(translator, sub.text)
                    sub.text = translated_text
                
                if progress_callback and i % 10 == 0:
                    progress_callback(f"📝 {filename}: {i+1}/{total_subs} dòng")
                
                if i % 10 == 0:
                    time.sleep(0.5)  # Tránh rate limit
        else:
            # Dịch batch
            batch_size = 20
            texts_to_translate = []
            text_mapping = {}
            
            for i, sub in enumerate(subs):
                if sub.text.strip():
                    texts_to_translate.append(sub.text)
                    text_mapping[sub.text] = i
            
            translated_texts = {}
            
            for i in range(0, len(texts_to_translate), batch_size):
                batch = texts_to_translate[i:i+batch_size]
                
                for text in batch:
                    translated = translate_text_with_retry(translator, text)
                    translated_texts[text] = translated
                    time.sleep(0.3)
                
                if progress_callback:
                    progress_callback(f"🚀 {filename}: batch {i//batch_size + 1}/{(len(texts_to_translate)-1)//batch_size + 1}")
            
            # Áp dụng bản dịch
            for sub in subs:
                if sub.text.strip() and sub.text in translated_texts:
                    sub.text = translated_texts[sub.text]
        
        result = srt_to_string(subs)
        
        if progress_callback:
            progress_callback(f"✅ Hoàn thành {filename}")
        
        return {
            'filename': filename,
            'content': result,
            'status': 'success',
            'subtitle_count': total_subs
        }
        
    except Exception as e:
        if progress_callback:
            progress_callback(f"❌ Lỗi {filename}: {str(e)}")
        
        return {
            'filename': filename,
            'content': None,
            'status': 'error',
            'error': str(e)
        }

def create_zip_file(translated_files):
    """Tạo file ZIP chứa các file đã dịch"""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_info in translated_files:
            if file_info['status'] == 'success':
                # Tạo tên file mới
                original_name = file_info['filename']
                name_without_ext = os.path.splitext(original_name)[0]
                new_filename = f"{name_without_ext}_vietnamese.srt"
                
                # Thêm vào ZIP
                zip_file.writestr(new_filename, file_info['content'])
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()

def display_translation_progress(files_count):
    """Hiển thị thanh tiến trình cho việc dịch nhiều file"""
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    return progress_bar, status_text

def display_srt_preview(srt_content, filename=""):
    """Hiển thị preview của file SRT"""
    try:
        subs = pysrt.from_string(srt_content)
        
        st.subheader(f"📺 Xem trước: {filename}")
        
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
        
        # Hiển thị 10 dòng đầu
        display_subs = subs[:10]
        if len(subs) > 10:
            st.info(f"Hiển thị 10/{len(subs)} dòng đầu tiên")
        
        for i, sub in enumerate(display_subs):
            with st.expander(f"Dòng {i+1}: {sub.start} --> {sub.end}"):
                st.write(sub.text)
        
    except Exception as e:
        st.error(f"❌ Lỗi khi hiển thị preview: {str(e)}")

def main():
    st.set_page_config(
        page_title="SRT Translator Pro - Multi Files",
        page_icon="🌐",
        layout="wide"
    )
    
    st.title("🌐 SRT Translator Pro - Dịch nhiều file")
    st.markdown("---")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Cài đặt")
        
        translation_method = st.radio(
            "Phương pháp dịch:",
            ["An toàn (từng dòng)", "Nhanh (batch)"],
            help="An toàn: chậm hơn nhưng ít lỗi. Nhanh: nhanh hơn nhưng có thể bị lỗi"
        )
        
        st.markdown("---")
        st.header("🆕 Tính năng mới")
        st.write("• ✅ Tải lên nhiều file cùng lúc")
        st.write("• ✅ Dịch nhiều file song song")
        st.write("• ✅ Tải xuống file ZIP")
        st.write("• ✅ Xem trước từng file")
        
        st.markdown("---")
        st.header("ℹ️ Thông tin")
        st.write("• Hỗ trợ file SRT không giới hạn")
        st.write("• Xử lý thông minh cho file lớn")
        st.write("• Progress tracking chi tiết")
    
    # File uploader - cho phép nhiều file
    uploaded_files = st.file_uploader(
        "📁 Chọn các file SRT cần dịch:",
        type=['srt'],
        accept_multiple_files=True,
        help="Có thể chọn nhiều file SRT cùng lúc"
    )
    
    if uploaded_files:
        st.success(f"✅ Đã tải {len(uploaded_files)} file(s)")
        
        # Hiển thị thông tin các file
        st.subheader("📋 Danh sách file:")
        
        total_size = 0
        total_subs = 0
        
        file_info_list = []
        
        for i, uploaded_file in enumerate(uploaded_files):
            try:
                # Đọc file
                try:
                    srt_content = uploaded_file.read().decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        uploaded_file.seek(0)
                        srt_content = uploaded_file.read().decode('utf-8-sig')
                    except:
                        uploaded_file.seek(0)
                        srt_content = uploaded_file.read().decode('latin-1')
                
                # Parse để lấy thông tin
                subs = pysrt.from_string(srt_content)
                file_size = len(srt_content)
                
                file_info = {
                    'name': uploaded_file.name,
                    'content': srt_content,
                    'size': file_size,
                    'subtitle_count': len(subs)
                }
                file_info_list.append(file_info)
                
                total_size += file_size
                total_subs += len(subs)
                
                # Hiển thị thông tin file
                with st.expander(f"📄 {uploaded_file.name}"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Số dòng", len(subs))
                    with col2:
                        st.metric("Kích thước", f"{file_size:,} ký tự")
                    with col3:
                        if subs:
                            duration = subs[-1].end - subs[0].start
                            st.metric("Thời lượng", str(duration))
                
            except Exception as e:
                st.error(f"❌ Lỗi đọc file {uploaded_file.name}: {str(e)}")
        
        # Thống kê tổng
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Tổng file", len(file_info_list))
        with col2:
            st.metric("Tổng dòng phụ đề", f"{total_subs:,}")
        with col3:
            st.metric("Tổng kích thước", f"{total_size:,} ký tự")
        with col4:
            estimated_time = total_subs * 0.5  # Ước tính 0.5s/dòng
            st.metric("Thời gian ước tính", f"{estimated_time/60:.1f} phút")
        
        # Cảnh báo
        if total_size > 50000:
            st.warning("⚠️ Tổng kích thước file khá lớn. Quá trình dịch có thể mất nhiều thời gian!")
        
        # Nút dịch
        if st.button("🚀 Bắt đầu dịch tất cả file", type="primary"):
            start_time = time.time()
            
            # Tạo progress tracking
            progress_container = st.container()
            with progress_container:
                overall_progress = st.progress(0)
                status_text = st.empty()
                detailed_status = st.empty()
            
            translated_files = []
            
            # Dịch từng file
            for i, file_info in enumerate(file_info_list):
                status_text.text(f"🔄 Đang dịch file {i+1}/{len(file_info_list)}: {file_info['name']}")
                
                def progress_callback(message):
                    detailed_status.text(message)
                
                # Dịch file
                result = translate_single_file(
                    file_info['content'], 
                    file_info['name'], 
                    translation_method,
                    progress_callback
                )
                
                translated_files.append(result)
                
                # Cập nhật progress
                overall_progress.progress((i + 1) / len(file_info_list))
                
                # Nghỉ giữa các file
                time.sleep(1)
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Lưu kết quả vào session state
            st.session_state.translated_files = translated_files
            st.session_state.translation_completed = True
            
            # Hiển thị kết quả
            success_count = sum(1 for f in translated_files if f['status'] == 'success')
            error_count = len(translated_files) - success_count
            
            if success_count > 0:
                st.success(f"🎉 Dịch hoàn thành! {success_count}/{len(translated_files)} file thành công trong {duration:.1f} giây")
            
            if error_count > 0:
                st.error(f"❌ {error_count} file gặp lỗi")
                
                # Hiển thị chi tiết lỗi
                with st.expander("Chi tiết lỗi:"):
                    for file_result in translated_files:
                        if file_result['status'] == 'error':
                            st.write(f"• {file_result['filename']}: {file_result.get('error', 'Unknown error')}")
        
        # Hiển thị tùy chọn sau khi dịch
        if st.session_state.get('translation_completed', False):
            st.markdown("---")
            st.subheader("🎯 Tùy chọn sau khi dịch:")
            
            translated_files = st.session_state.get('translated_files', [])
            success_files = [f for f in translated_files if f['status'] == 'success']
            
            if success_files:
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("👁️ Xem trước các file", use_container_width=True):
                        st.session_state.show_preview = True
                
                with col2:
                    # Tạo ZIP file
                    zip_data = create_zip_file(success_files)
                    
                    st.download_button(
                        label=f"💾 Tải xuống {len(success_files)} file (.zip)",
                        data=zip_data,
                        file_name=f"translated_srt_files_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                
                # Tải xuống từng file riêng lẻ
                st.subheader("📥 Tải xuống từng file:")
                
                cols = st.columns(min(3, len(success_files)))
                for i, file_result in enumerate(success_files):
                    col_idx = i % len(cols)
                    with cols[col_idx]:
                        original_name = file_result['filename']
                        name_without_ext = os.path.splitext(original_name)[0]
                        new_filename = f"{name_without_ext}_vietnamese.srt"
                        
                        st.download_button(
                            label=f"📄 {original_name}",
                            data=file_result['content'],
                            file_name=new_filename,
                            mime="text/plain",
                            use_container_width=True
                        )
                
                # Hiển thị preview nếu được yêu cầu
                if st.session_state.get('show_preview', False):
                    st.markdown("---")
                    
                    # Chọn file để preview
                    selected_file = st.selectbox(
                        "Chọn file để xem trước:",
                        options=range(len(success_files)),
                        format_func=lambda x: success_files[x]['filename']
                    )
                    
                    if selected_file is not None:
                        file_to_preview = success_files[selected_file]
                        display_srt_preview(file_to_preview['content'], file_to_preview['filename'])
    
    else:
        st.info("👆 Vui lòng chọn các file SRT để bắt đầu")
        
        # Reset session state
        if 'translated_files' in st.session_state:
            del st.session_state.translated_files
        if 'translation_completed' in st.session_state:
            del st.session_state.translation_completed
        if 'show_preview' in st.session_state:
            del st.session_state.show_preview
        
        # Hướng dẫn
        with st.expander("📚 Hướng dẫn sử dụng - Phiên bản nhiều file"):
            st.markdown("""
            ### 🔧 Cách sử dụng:
            
            1. **Chọn nhiều file SRT** cùng lúc (Ctrl+Click hoặc Shift+Click)
            2. **Xem thông tin** các file đã chọn
            3. **Chọn phương pháp dịch** phù hợp
            4. **Nhấn "Bắt đầu dịch"** và chờ đợi
            5. **Tải xuống file ZIP** hoặc từng file riêng lẻ
            
            ### 🆕 Tính năng mới:
            - ✅ **Multi-file upload:** Chọn nhiều file cùng lúc
            - ✅ **Batch translation:** Dịch nhiều file song song  
            - ✅ **ZIP download:** Tải xuống tất cả file trong 1 file ZIP
            - ✅ **Individual download:** Tải xuống từng file riêng
            - ✅ **Preview system:** Xem trước từng file đã dịch
            - ✅ **Progress tracking:** Theo dõi tiến trình chi tiết
            
            ### 💡 Lưu ý:
            - Càng nhiều file càng mất nhiều thời gian
            - Không tắt trang trong khi dịch
            - Kiểm tra kết quả trước khi sử dụng
            - File lỗi sẽ được báo cáo riêng
            """)

if __name__ == "__main__":
    main()
