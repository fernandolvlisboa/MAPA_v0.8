"""
ImagePreprocessor — Pré-processamento de imagens para OCR

Melhora a qualidade de imagens antes do OCR através de técnicas como:
- Binarização (threshold)
- Remoção de ruído (denoising)
- Correção de rotação (deskew)
- Ajuste de contraste
"""

from __future__ import annotations

from typing import Literal

import cv2
import numpy as np
from PIL import Image


class ImagePreprocessor:
    """Pré-processador de imagens para melhorar resultados de OCR."""

    @staticmethod
    def binarize(
        image: np.ndarray | Image.Image,
        method: Literal["otsu", "adaptive", "simple"] = "otsu",
        threshold: int = 127,
    ) -> np.ndarray:
        """
        Binariza a imagem (converte para preto e branco).

        Args:
            image: Imagem PIL ou array numpy
            method: Método de binarização
                - "otsu": Threshold automático de Otsu
                - "adaptive": Threshold adaptativo
                - "simple": Threshold simples
            threshold: Valor de threshold para método "simple"

        Returns:
            Imagem binarizada como array numpy
        """
        # Converte PIL para numpy se necessário
        if isinstance(image, Image.Image):
            image = np.array(image)

        # Converte para escala de cinza se necessário
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if len(image.shape) == 3 else image

        # Aplica binarização
        if method == "otsu":
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        elif method == "adaptive":
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )
        else:  # simple
            _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

        return binary

    @staticmethod
    def denoise(
        image: np.ndarray | Image.Image,
        method: Literal["gaussian", "median", "bilateral"] = "median",
        kernel_size: int = 3,
    ) -> np.ndarray:
        """
        Remove ruído da imagem.

        Args:
            image: Imagem PIL ou array numpy
            method: Método de denoising
                - "gaussian": Gaussian blur
                - "median": Median blur
                - "bilateral": Bilateral filter (preserva bordas)
            kernel_size: Tamanho do kernel (deve ser ímpar)

        Returns:
            Imagem sem ruído como array numpy
        """
        if isinstance(image, Image.Image):
            image = np.array(image)

        # Garante que kernel_size é ímpar
        if kernel_size % 2 == 0:
            kernel_size += 1

        if method == "gaussian":
            denoised = cv2.GaussianBlur(image, (kernel_size, kernel_size), 0)
        elif method == "median":
            denoised = cv2.medianBlur(image, kernel_size)
        else:  # bilateral
            denoised = cv2.bilateralFilter(image, kernel_size, 75, 75)

        return denoised

    @staticmethod
    def adjust_contrast(
        image: np.ndarray | Image.Image,
        method: Literal["clahe", "normalize", "gamma"] = "clahe",
        clip_limit: float = 2.0,
        gamma: float = 1.2,
    ) -> np.ndarray:
        """
        Ajusta o contraste da imagem.

        Args:
            image: Imagem PIL ou array numpy
            method: Método de ajuste
                - "clahe": Contrast Limited Adaptive Histogram Equalization
                - "normalize": Normalização simples
                - "gamma": Correção gamma
            clip_limit: Limite para CLAHE
            gamma: Valor gamma para correção gamma

        Returns:
            Imagem com contraste ajustado
        """
        if isinstance(image, Image.Image):
            image = np.array(image)

        # Converte para escala de cinza se necessário
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if len(image.shape) == 3 else image

        if method == "clahe":
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
        elif method == "normalize":
            enhanced = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
        else:  # gamma
            inv_gamma = 1.0 / gamma
            table = np.array(
                [((i / 255.0) ** inv_gamma) * 255 for i in range(256)]
            ).astype("uint8")
            enhanced = cv2.LUT(gray, table)

        return enhanced

    @staticmethod
    def deskew(image: np.ndarray | Image.Image) -> np.ndarray:
        """
        Corrige rotação da imagem (deskew).

        Args:
            image: Imagem PIL ou array numpy

        Returns:
            Imagem corrigida
        """
        if isinstance(image, Image.Image):
            image = np.array(image)

        # Converte para escala de cinza
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if len(image.shape) == 3 else image

        # Binariza
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

        # Detecta ângulo
        coords = np.column_stack(np.where(thresh > 0))
        angle = cv2.minAreaRect(coords)[-1]

        # Ajusta ângulo
        angle = -(90 + angle) if angle < -45 else -angle

        # Rotaciona se necessário (só corrige ângulos significativos)
        if abs(angle) > 0.5:
            (h, w) = image.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(
                image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
            )
            return rotated

        return image

    @staticmethod
    def resize_for_ocr(
        image: np.ndarray | Image.Image, target_dpi: int = 300, current_dpi: int = 72
    ) -> np.ndarray:
        """
        Redimensiona imagem para DPI ideal para OCR (300 DPI).

        Args:
            image: Imagem PIL ou array numpy
            target_dpi: DPI alvo
            current_dpi: DPI atual da imagem

        Returns:
            Imagem redimensionada
        """
        if isinstance(image, Image.Image):
            image = np.array(image)

        # Calcula fator de escala
        scale = target_dpi / current_dpi

        # Redimensiona apenas se necessário
        if abs(scale - 1.0) > 0.1:
            width = int(image.shape[1] * scale)
            height = int(image.shape[0] * scale)
            resized = cv2.resize(
                image,
                (width, height),
                interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA,
            )
            return resized

        return image

    @classmethod
    def preprocess_for_ocr(
        cls,
        image: np.ndarray | Image.Image,
        apply_deskew: bool = True,
        apply_denoise: bool = True,
        apply_contrast: bool = True,
        apply_binarize: bool = True,
    ) -> np.ndarray:
        """
        Pipeline completo de pré-processamento para OCR.

        Aplica todas as melhorias na ordem ideal.

        Args:
            image: Imagem PIL ou array numpy
            apply_deskew: Se deve corrigir rotação
            apply_denoise: Se deve remover ruído
            apply_contrast: Se deve ajustar contraste
            apply_binarize: Se deve binarizar

        Returns:
            Imagem pré-processada pronta para OCR
        """
        processed = image

        # 1. Redimensiona para DPI ideal
        processed = cls.resize_for_ocr(processed)

        # 2. Corrige rotação
        if apply_deskew:
            processed = cls.deskew(processed)

        # 3. Remove ruído
        if apply_denoise:
            processed = cls.denoise(processed, method="bilateral")

        # 4. Ajusta contraste
        if apply_contrast:
            processed = cls.adjust_contrast(processed, method="clahe")

        # 5. Binariza
        if apply_binarize:
            processed = cls.binarize(processed, method="otsu")

        return processed
