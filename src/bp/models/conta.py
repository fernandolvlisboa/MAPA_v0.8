"""
Pydantic models for accounting accounts (Conta).
"""


from pydantic import BaseModel, Field, field_validator


class ContaModel(BaseModel):
    codigo: str = Field(..., description="Código da conta, ex: 1.1.01")
    descricao: str = Field("", description="Descrição da conta")
    tipo: str | None = Field(None, description="Tipo (ATIVO, PASSIVO, RECEITA, etc)")
    natureza: str | None = Field(None, description="Natureza (Devedora/Credora)")
    nivel: int | None = Field(None, description="Nível hierárquico")
    parent_id: str | None = Field(None, description="Código da conta pai")
    forms: list[str] | None = Field(
        default_factory=list, description="Abas/origens em que aparece"
    )
    formula: str | None = Field(None, description="Fórmula/expressão ligada à conta")
    formato: str | None = Field(None, description="Formato de apresentação")
    tipo_do_lancamento: str | None = Field(None, description="Tipo de lançamento")
    relacao: str | None = Field(None, description="Relação com outras contas")

    @field_validator("codigo")
    def codigo_nao_vazio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("codigo não pode ser vazio")
        return v.strip()

    @field_validator("descricao")
    def descricao_strip(cls, v: str | None) -> str:
        return (v or "").strip()
