import os
import re
from typing import List, Dict, Any

class MultiModalProcessor:
    def get_cleaning_strategies(self, modality: str) -> List[Dict[str, Any]]:
        if modality == "image":
            return [
                {
                    "key": "image_deduplicate",
                    "name": "图像去重复 (aHash)",
                    "description": "基于平均哈希检测重复图像并生成“去重”建议",
                    "implemented": True,
                    "default_enabled": True,
                    "params_schema": {
                        "hamming_threshold": {"type": "int", "default": 0, "min": 0, "max": 16}
                    }
                },
                {
                    "key": "image_blur_detect",
                    "name": "模糊检测",
                    "description": "检测模糊图像并生成“去模糊”建议",
                    "implemented": True,
                    "default_enabled": True,
                    "params_schema": {}
                }
            ]
        if modality == "text":
            return [
                {
                    "key": "text_placeholder",
                    "name": "文本清洗 (预留)",
                    "description": "后续扩展文本清洗算法",
                    "implemented": False,
                    "default_enabled": False,
                    "params_schema": {}
                }
            ]
        if modality == "tabular":
            return [
                {
                    "key": "tabular_placeholder",
                    "name": "表格清洗 (预留)",
                    "description": "后续扩展表格缺失值/重复行等清洗算法",
                    "implemented": False,
                    "default_enabled": False,
                    "params_schema": {}
                }
            ]
        return []

    def compute_image_ahash(self, image_path: str) -> str:
        try:
            import cv2
            import numpy as np

            gray_image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if gray_image is None:
                return ""
            resized = cv2.resize(gray_image, (8, 8), interpolation=cv2.INTER_AREA)
            average_gray = resized.mean()
            hash_bits = (resized > average_gray).astype(np.uint8).flatten()
            hash_value = 0
            for bit in hash_bits:
                hash_value = (hash_value << 1) | int(bit)
            return f"{hash_value:016x}"
        except Exception:
            return ""

    def hamming_distance_hex64(self, hex_a: str, hex_b: str) -> int:
        try:
            left_hash = int(hex_a, 16)
            right_hash = int(hex_b, 16)
        except Exception:
            return 999
        diff_bits = left_hash ^ right_hash
        try:
            return diff_bits.bit_count()
        except Exception:
            count = 0
            while diff_bits:
                diff_bits &= diff_bits - 1
                count += 1
            return count

    def clean_image(self, image_path: str, parameters: Dict[str, Any]):
        """清洗图像数据"""
        try:
            import cv2

            image = cv2.imread(image_path)
            if image is None:
                return False
            
            if parameters.get('deblur', False):
                image = self._deblur_image(image)
            
            if 'resize' in parameters:
                width = parameters['resize'].get('width', image.shape[1])
                height = parameters['resize'].get('height', image.shape[0])
                image = cv2.resize(image, (width, height))
            
            if parameters.get('denoise', False):
                image = cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)
            
            cv2.imwrite(image_path, image)
            return True
        except Exception:
            return False

    def clean_text(self, text_path: str, parameters: Dict[str, Any]):
        """清洗文本数据"""
        try:
            with open(text_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            
            if parameters.get('remove_whitespace', True):
                text = re.sub(r'\s+', ' ', text).strip()
            
            if parameters.get('remove_special_chars', False):
                text = re.sub(r'[^\w\s]', '', text)
            
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(text)
            return True
        except Exception:
            return False

    def clean_tabular(self, tabular_path: str, parameters: Dict[str, Any]):
        """清洗表格数据"""
        try:
            pd = self._load_pandas()

            if tabular_path.endswith('.csv'):
                df = pd.read_csv(tabular_path)
            elif tabular_path.endswith('.xlsx'):
                df = pd.read_excel(tabular_path)
            else:
                return False
            
            if parameters.get('handle_missing', True):
                df = df.fillna(parameters.get('fill_value', 0))
            
            if parameters.get('remove_duplicates', True):
                df = df.drop_duplicates()
            
            if tabular_path.endswith('.csv'):
                df.to_csv(tabular_path, index=False)
            elif tabular_path.endswith('.xlsx'):
                df.to_excel(tabular_path, index=False)
            return True
        except Exception:
            return False

    def detect_quality_issues(self, sample_path: str, sample_type: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检测质量问题"""
        issues = []
        
        if sample_type == 'image':
            issues.extend(self._detect_image_issues(sample_path, parameters))
        elif sample_type == 'text':
            issues.extend(self._detect_text_issues(sample_path, parameters))
        elif sample_type == 'tabular':
            issues.extend(self._detect_tabular_issues(sample_path, parameters))
        
        return issues

    def _detect_image_issues(self, image_path: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检测图像质量问题"""
        issues = []
        
        try:
            import cv2

            image = cv2.imread(image_path)
            if image is None:
                issues.append({
                    'suggestion': '无效图像',
                    'confidence': 1.0
                })
                return issues
            
            if parameters.get('detect_blur', True):
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                laplacian = cv2.Laplacian(gray, cv2.CV_64F)
                blur_score = laplacian.var()
                if blur_score < 100:
                    issues.append({
                        'suggestion': '去模糊',
                        'confidence': 1.0 - (blur_score / 100)
                    })
            
            if parameters.get('detect_contrast', True):
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                min_val, max_val, _, _ = cv2.minMaxLoc(gray)
                contrast = (max_val - min_val) / (max_val + min_val) if (max_val + min_val) > 0 else 0
                if contrast < 0.3:
                    issues.append({
                        'suggestion': '增强对比度',
                        'confidence': 1.0 - contrast / 0.3
                    })
        except Exception:
            pass
        
        return issues

    def _detect_text_issues(self, text_path: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检测文本质量问题"""
        issues = []
        
        try:
            with open(text_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            
            if len(text.strip()) == 0:
                issues.append({
                    'suggestion': '空文本',
                    'confidence': 1.0
                })
            
            if parameters.get('min_length', 0) > 0:
                if len(text) < parameters['min_length']:
                    issues.append({
                        'suggestion': '文本过短',
                        'confidence': 1.0 - (len(text) / parameters['min_length'])
                    })
        except Exception:
            pass
        
        return issues

    def _detect_tabular_issues(self, tabular_path: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检测表格质量问题"""
        issues = []
        
        try:
            pd = self._load_pandas()

            if tabular_path.endswith('.csv'):
                df = pd.read_csv(tabular_path)
            elif tabular_path.endswith('.xlsx'):
                df = pd.read_excel(tabular_path)
            else:
                return issues
            
            if parameters.get('detect_missing', True):
                missing_count = df.isnull().sum().sum()
                total_cells = df.shape[0] * df.shape[1]
                if total_cells > 0:
                    missing_ratio = missing_count / total_cells
                    if missing_ratio > 0.1:
                        issues.append({
                            'suggestion': '处理缺失值',
                            'confidence': missing_ratio
                        })
            
            if parameters.get('detect_duplicates', True):
                duplicate_count = df.duplicated().sum()
                if duplicate_count > 0:
                    issues.append({
                        'suggestion': '去重',
                        'confidence': min(1.0, duplicate_count / len(df))
                    })
        except Exception:
            pass
        
        return issues

    def _deblur_image(self, img):
        """去模糊图像"""
        import cv2
        import numpy as np

        sharpen_kernel = np.array([[1, 1, 1], [1, -8, 1], [1, 1, 1]])
        return cv2.filter2D(img, -1, sharpen_kernel)

    def _load_pandas(self):
        try:
            import pandas as pd
            return pd
        except Exception as exc:
            raise RuntimeError(
                "Tabular processing requires a working pandas installation. "
                "Check numpy/pandas/pyarrow binary compatibility."
            ) from exc
