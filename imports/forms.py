from django import forms


class CashbookUploadForm(forms.Form):
    file = forms.FileField(
        label="Archivo de importación",
        help_text=(
            "JSON Elemental v1, XLSX del libro de caja o CSV histórico UTF-8. "
            "La carga solo genera una previsualización."
        ),
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".json,.xlsx,.csv,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
            }
        ),
    )


CsvUploadForm = CashbookUploadForm
