import os
import shutil
from typing import Dict, Any

from ..models.dataset import Dataset
from ..models.sample import Sample
from ..database import SessionLocal

class FileProcessor:
    def process_file(self, file, dataset_id: int) -> Dict[str, Any]:
        """处理上传的文件"""
        db = SessionLocal()
        try:
            dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
            if not dataset:
                return {"status": "error", "message": "数据集不存在"}
            
            storage_path = dataset.storage_path
            os.makedirs(storage_path, exist_ok=True)
            
            file_path = os.path.join(storage_path, file.filename)
            with open(file_path, "wb") as target_file:
                shutil.copyfileobj(file.file, target_file)
            
            metadata = self.extract_metadata(file_path, file.content_type)
            
            if not self.validate_file(file_path, file.content_type):
                os.remove(file_path)
                return {"status": "error", "message": "文件验证失败"}
            
            sample = Sample(
                dataset_id=dataset_id,
                name=file.filename,
                path=file_path,
                size=os.path.getsize(file_path),
                type=file.content_type.split("/")[0],
                sample_metadata=metadata
            )
            db.add(sample)
            db.commit()
            
            return {"status": "success", "message": "文件上传成功", "file_id": sample.id}
        finally:
            db.close()

    def process_folder(self, folder_path: str, dataset_id: int, include_subfolders: bool = True) -> Dict[str, Any]:
        """处理导入的文件夹"""
        db = SessionLocal()
        try:
            if not os.path.isdir(folder_path):
                return {"status": "error", "message": "文件夹不存在"}
            
            dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
            if not dataset:
                return {"status": "error", "message": "数据集不存在"}
            
            storage_path = dataset.storage_path
            os.makedirs(storage_path, exist_ok=True)
            
            processed_count = 0
            for root, _dirs, file_names in os.walk(folder_path):
                if not include_subfolders and root != folder_path:
                    continue
                
                for file_name in file_names:
                    source_path = os.path.join(root, file_name)
                    relative_path = os.path.relpath(source_path, folder_path)
                    stored_path = os.path.join(storage_path, relative_path)
                    os.makedirs(os.path.dirname(stored_path), exist_ok=True)
                    shutil.copy2(source_path, stored_path)
                    
                    import mimetypes
                    file_type, _ = mimetypes.guess_type(source_path)
                    if not file_type:
                        file_type = "application/octet-stream"
                    
                    metadata = self.extract_metadata(stored_path, file_type)
                    
                    if self.validate_file(stored_path, file_type):
                        sample = Sample(
                            dataset_id=dataset_id,
                            name=relative_path,
                            path=stored_path,
                            size=os.path.getsize(stored_path),
                            type=file_type.split("/")[0],
                            sample_metadata=metadata
                        )
                        db.add(sample)
                        processed_count += 1
            
            db.commit()
            return {"status": "success", "message": f"文件夹导入成功，处理了 {processed_count} 个文件"}
        finally:
            db.close()

    def extract_metadata(self, file_path: str, file_type: str) -> Dict[str, Any]:
        """提取文件元数据"""
        metadata = {}
        
        if file_type.startswith("image/"):
            try:
                from PIL import Image
                with Image.open(file_path) as img:
                    metadata["width"] = img.width
                    metadata["height"] = img.height
                    metadata["format"] = img.format
            except Exception:
                pass
        elif file_type.startswith("audio/"):
            try:
                import mutagen
                audio = mutagen.File(file_path)
                if audio:
                    metadata["duration"] = audio.info.length if hasattr(audio.info, 'length') else None
                    metadata["format"] = audio.info.format if hasattr(audio.info, 'format') else None
            except Exception:
                pass
        elif file_type.startswith("text/") or file_type == "application/json" or file_type == "application/csv":
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as text_file:
                    content = text_file.read()
                    metadata["lines"] = len(content.splitlines())
                    metadata["characters"] = len(content)
            except Exception:
                pass
        
        return metadata

    def validate_file(self, file_path: str, file_type: str) -> bool:
        """验证文件有效性"""
        if os.path.getsize(file_path) == 0:
            return False
        
        if file_type.startswith("image/"):
            try:
                from PIL import Image
                with Image.open(file_path) as img:
                    img.verify()
                return True
            except Exception:
                return False
        elif file_type.startswith("audio/"):
            try:
                import mutagen
                audio = mutagen.File(file_path)
                return audio is not None
            except Exception:
                return False
        elif file_type.startswith("text/") or file_type == "application/json" or file_type == "application/csv":
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as text_file:
                    text_file.read()
                return True
            except Exception:
                return False
        
        return True
