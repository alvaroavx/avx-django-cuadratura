from django import forms


class CsvUploadForm(forms.Form):
    file = forms.FileField(
        label="Archivo CSV",
        help_text="CSV UTF-8, máximo 2 MiB y 500 filas. La carga solo genera una previsualización.",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}),
    )

