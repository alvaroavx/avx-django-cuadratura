from django import forms


class CashbookUploadForm(forms.Form):
    file = forms.FileField(
        label="Libro de caja",
        help_text=(
            "XLSX en el formato del libro de caja o CSV UTF-8. "
            "Se leerá la hoja del período activo y la carga solo generará una previsualización."
        ),
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
            }
        ),
    )


CsvUploadForm = CashbookUploadForm
