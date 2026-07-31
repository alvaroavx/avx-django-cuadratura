from django import forms

class CloseForm(forms.Form):
    second_category_withholding=forms.IntegerField(label="Retención segunda categoría (manual)",min_value=0,initial=0)
    ppm=forms.IntegerField(label="PPM (manual)",min_value=0,initial=0)

class ReopenForm(forms.Form):
    reason=forms.CharField(label="Motivo de reapertura",min_length=5,widget=forms.Textarea)

