import uuid
from django import forms
from documents.models import ElectronicReceipt
from .models import Sale

class ManualOperationForm(forms.Form):
    total=forms.IntegerField(label="Monto total pagado",min_value=1,widget=forms.NumberInput(attrs={"inputmode":"numeric"}))
    payment_date=forms.DateField(label="Fecha del pago",widget=forms.DateInput(attrs={"type":"date"}))
    operation_date=forms.DateField(label="Fecha de la operación",widget=forms.DateInput(attrs={"type":"date"}))
    transfer_reference=forms.CharField(label="Referencia de transferencia",max_length=160,required=False)
    detail=forms.CharField(label="Detalle",max_length=500)
    classification=forms.ChoiceField(label="Clasificación",choices=Sale.TaxClassification.choices)
    customer_name=forms.CharField(label="Cliente o receptor",max_length=200,required=False)
    customer_tax_id=forms.CharField(label="RUT receptor",max_length=12,required=False)
    observations=forms.CharField(label="Observaciones",required=False,widget=forms.Textarea(attrs={"rows":3}))
    idempotency_key=forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)

class ReceiptForm(forms.Form):
    document_type=forms.TypedChoiceField(label="Tipo de boleta",choices=ElectronicReceipt.DocumentType.choices,coerce=int)
    folio=forms.IntegerField(min_value=1)
    tax_issue_date=forms.DateField(label="Fecha tributaria de emisión",widget=forms.DateInput(attrs={"type":"date"}))
    issuer_name=forms.CharField(label="Emisor tributario",max_length=200,required=False)
    signer_name=forms.CharField(label="Vendedor o firmante",max_length=200,required=False)

