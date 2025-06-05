'------------------------------------------------------------------
' Seebeck Measurement Program
'       by KEITHLEY 2182A & KEITHLEY 2700 (ver.1.0, 2016/07/26)
'------------------------------------------------------------------

'                       2016/10/18: ver.1.0: ‘ª’èƒvƒƒOƒ‰ƒ€ƒŠƒŠ[ƒX by Y.SUZUKI
'
    Dim bCancel As Boolean  'ƒNƒCƒbƒgƒ{ƒ^ƒ“‚ÌŽÀs—L–³
Private Declare Function GetTickCount Lib "kernel32" () As Long
Private Declare Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As Long)
Private Sub CommandButton1_Click()
Dim j As Integer
Dim kaisuu1 As Integer
Dim kaisuu2 As Integer
Dim kaisuu3 As Integer
Dim kaisuu4 As Integer
Dim kaisuu As Integer
Dim tcTime As Double

Dim v0 As Double
Dim v1 As Double
Dim incRate As Double
Dim decRate As Double
Dim preTime As Integer
Dim periodTime As Integer
Dim holdTime As Integer

Dim volt As Double          'ƒq[ƒ^“dˆ³Ši”[•Ï”
Dim temf As Double          '”M‹N“d—ÍŠi”[•Ï”
Dim temp1 As Double         '‰·“xŠi”[•Ï”
Dim temp2 As Double         '‰·“xŠi”[•Ï”
Const addr1 As Integer = 7  '2182A‚ÌIEEEƒAƒhƒŒƒX
Const addr2 As Integer = 16 '2700‚ÌIEEEƒAƒhƒŒƒX
Const addr3 As Integer = 15 'PK160‚ÌIEEEƒAƒhƒŒƒX
v0 = StartVolt.Value 'ƒq[ƒ^[“d—¬‚Ì‰Šú’l
v1 = StopVolt.Value 'ƒq[ƒ^[“d—¬‚Ì–Ú•W’l
incRate = HeatingRate.Value / 1000 'ƒq[ƒ^[“d—¬‚Ìã¸—¦[A/s]
decRate = CoolingRate.Value / 1000 'ƒq[ƒ^[“d—¬‰º~—¦[A/a]
periodTime = Period.Value '‘ª’èŠÔŠu
holdTime = Hold.Value 'Å‚‰·“x•ÛŽŽžŠÔ
preTime = Pre.Value '¸‰·‘Ò‚¿ŽžŠÔ

Application.StatusBar = "Initializing"  'ƒXƒe[ƒ^ƒXƒo[‚É‘ª’èŠJŽn‚ð•\Ž¦
QuitButton.SetFocus         'ƒNƒCƒbƒgƒ{ƒ^ƒ“‚ÉƒtƒH[ƒJƒX
bCancel = False             'ƒNƒCƒbƒgƒ{ƒ^ƒ“‚Ì‰Šú’l

'@‘ª’èŒ‹‰ÊƒV[ƒg‚Ì€”õ
Cells.Clear                         'ƒV[ƒg‚Ì‹ó”’‰»
    
With Range("A1")                    '—ñ‚P‚ÌÝ’è
    .ColumnWidth = 8                'ƒZƒ‹•
    .Interior.ColorIndex = 35       'ƒZƒ‹”wŒiFi”–—Îj
    .HorizontalAlignment = xlCenter '•¶Žš—ñ‚ÌˆÊ’ui’†‰›j
    .Value = "Time [s]"             'ƒ^ƒCƒgƒ‹E‘ª’èŽžŠÔ
End With
    
With Range("B1")                    '—ñ‚Q‚ÌÝ’è
    .ColumnWidth = 12               'ƒZƒ‹•
    .Interior.ColorIndex = 34       'ƒZƒ‹”wŒiFi”–Âj
    .HorizontalAlignment = xlCenter '•¶Žš—ñ‚ÌˆÊ’ui’†‰›j
    .Value = "TEMF [mV]"            'ƒ^ƒCƒgƒ‹E•\–Ê“dˆÊ
End With
    
With Range("C1")                    '—ñ‚R‚ÌÝ’è
    .ColumnWidth = 12               'ƒZƒ‹•
    .Interior.ColorIndex = 35       'ƒZƒ‹”wŒiFi”–—Îj
    .HorizontalAlignment = xlCenter '•¶Žš—ñ‚ÌˆÊ’ui’†‰›j
    .Value = "Temp1[oC]"           'ƒ^ƒCƒgƒ‹E‰·“x
End With

With Range("D1")                    '—ñ‚R‚ÌÝ’è
    .ColumnWidth = 12               'ƒZƒ‹•
    .Interior.ColorIndex = 34       'ƒZƒ‹”wŒiFi”–—Îj
    .HorizontalAlignment = xlCenter '•¶Žš—ñ‚ÌˆÊ’ui’†‰›j
    .Value = "Temp2[oC]"           'ƒ^ƒCƒgƒ‹E‰·“x
End With
    
Application.StatusBar = "‘ª’èŠJŽn"  'ƒXƒe[ƒ^ƒXƒo[‚ðƒŠƒZƒbƒg

initialize 21, 0            '‘ª’è‹@Ší‚Ì‰Šú‰»
send addr1, "*RST", stat%   '2182A‚Ì‰Šú‰»
send addr2, "*RST", stat%   '2700‚Ì‰Šú‰»
    
'PK160‚Ì‰ŠúÝ’è
    
send addr3, "#1 REN", stat%     'ƒŠƒ‚[ƒg§ŒäƒIƒ“
send addr3, "#1 VCN 100", stat% 'CC§Œä‚Ì‚½‚ßo—Í‚ðÅ‘å’èŠi“dˆ³‚ÉÝ’è
send addr3, "#1 OCP 100", stat% 'CC§Œä‚Ì‚½‚ß‰ß“d—¬•ÛŒì’l‚ðÅ‘å‰ß“d—¬•ÛŒì’l‚ÉÝ’è
send addr3, "#1 SW1", stat%     'o—Í‰Â”\ó‘Ô

'@“dˆ³E‰·“x‘ª’è‹@Šíƒpƒ‰ƒ[ƒ^‚ÌÝ’è
'    Configure voltage for KEITHLEY 2182A
'send addr1, ":CHAN 1", stat%
send addr1, ":CONF:volt", stat%
send addr1, ":VOLT:DIGITS 8", stat%
send addr1, ":VOLT:NPLC 5", stat%     '‘ª’è¸“x‚ÌÝ’è
        
'    Configure Temperature for KEITHLEY2700
send addr2, ":CONF:TEMP", stat%           '‰·“xƒ‚[ƒh‚Ì‘I‘ð
send addr2, ":UNIT:TEMP C", stat%           '‰·“x’PˆÊ‚ÌÝ’è
send addr2, ":TEMP:TRAN TC", stat%          '”M“d‘Îƒ‚[ƒh‚Ì‘I‘ð"
send addr2, ":TEMP:TC:TYPE K", stat%        '”M“d‘Îƒ^ƒCƒv‚ÌÝ’è"
send addr2, ":TEMP:TC:RJUN:RSEL EXT", stat% '–Í‹[Šî€Ú“_‚Ì‘I‘ð"
'         send addr2, ":TEMP:TC:RJUN:SIM 0", stat%   'Šî€‰·“x‚ÌÝ’è
send addr2, ":TEMP:NPLC 5", stat%          '‘ª’è¸“x‚ÌÝ’è

'Šeƒq[ƒ^“®ìðŒ‚É‚¨‚¯‚é‘ª’è‰ñ”‚ÌŒvŽZ
If preTime Mod periodTime = 0 Then
    kaisuu1 = preTime \ periodTime
    Else
        kaisuu1 = preTime \ periodTime + 1
End If

If (v1 - v0) / incRate Mod periodTime = 0 Then
    kaisuu2 = ((v1 - v0) / incRate) \ periodTime
    Else
        kaisuu2 = ((v1 - v0) / incRate) \ periodTime + 1
End If

If holdTime Mod periodTime = 0 Then
    kaisuu3 = holdTime \ periodTime
    Else
        kaisuu3 = holdTime \ periodTime + 1
End If

If (v1 - v0) / decRate Mod periodTime = 0 Then
    kaisuu4 = ((v1 - v0) / decRate) \ periodTime
    Else
        kaisuu4 = ((v1 - v0) / decRate) \ periodTime + 1
End If

Do While v1 - incRate * kaisuu2 * periodTime < 0
    kaisuu2 = kaisuu2 - 1
Loop

Do While v1 - decRate * kaisuu4 * periodTime < 0
    kaisuu4 = kaisuu4 - 1
Loop

volt = v0  'ƒq[ƒ^[“dˆ³
send addr3, "#1 ISET" & volt, stat%


j = 2
kaisuu = 1
Sleep 2000

Do While bCancel = False
    tcTime = GetTickCount
    
    Select Case kaisuu
        Case 1 To kaisuu1
            volt = v0
        Case kaisuu1 + 1 To kaisuu1 + kaisuu2
            volt = volt + incRate * periodTime
        Case kaisuu1 + kaisuu2 + 1 To kaisuu1 + kaisuu2 + kaisuu3
            volt = v1
        Case kaisuu1 + kaisuu2 + kaisuu3 + 1 To kaisuu1 + kaisuu2 + kaisuu3 + kaisuu4
            volt = volt - 1 * decRate * periodTime
        Case Is > kaisuu1 + kaisuu2 + kaisuu3 + kaisuu4
            volt = v0
    End Select
       
    send addr3, "#1 ISET" & volt, stat%
  
    Cells(j, 1).Value = (j - 2) * periodTime
    'TEMF‚Ì‘ª’è
    'Measure voltage on Channel 1 for KEITHLEY 2182A

    send addr1, ":READ?", stat%
    enter r$, 255, l%, addr1, stat%
    temf = Val(r$) * 1000
    Cells(j, 2).Value = temf                '—ñ‚Q‚É•\–Ê“dˆÊ‚ð[mV]’PˆÊ‚Å“ü—Í
        
    '‰·“x‚Ì‘ª’è
    'Measure temperature for KEITHLEY 2700
    send addr2, ":ROUT:CLOS (@102)", stat%
    send addr2, ":READ?", stat%
    enter r$, 255, l%, addr2, stat%
    temp1 = Val(r$)
    Cells(j, 3).Value = temp1              '—ñ‚R‚É‰·“x1‚ð[oC]’PˆÊ‚Å“ü—Í
    
    send addr2, ":ROUT:CLOS (@104)", stat%
    send addr2, ":READ?", stat%
    enter r$, 255, l%, addr2, stat%
    temp2 = Val(r$)
    Cells(j, 4).Value = temp2              '—ñ‚R‚É‰·“x1‚ð[oC]’PˆÊ‚Å“ü—Í
    
    Application.StatusBar = "Measuring :" & (j - 2) * periodTime & "[s], " & temf & "[mV], " & temp1 & "[C], " & temp2 & "[C]"
    


    
    j = j + 1
    kaisuu = kaisuu + 1
    
    If GetTickCount - tcTime < periodTime * 1000 Then
        Sleep (periodTime * 1000 - GetTickCount + tcTime)
    End If

DoEvents
Loop

send addr3, "#1 SW0", stat%
Application.StatusBar = "Done"  'ƒXƒe[ƒ^ƒXƒo[‚É‘ª’èI—¹‚ð•\Ž¦
SaveButton.SetFocus                 'ƒZ[ƒuƒ{ƒ^ƒ“‚ÉƒtƒH[ƒJƒX
     
End Sub





Private Sub CoolingRate_Change()

End Sub

Private Sub QuitButton_Click()

    bCancel = True      'ƒNƒCƒbƒgƒ{ƒ^ƒ“‚Ìˆ—
    
End Sub





Private Sub SaveButton_Click()

    Dim newFN As String                         'V‹Kì¬ƒtƒ@ƒCƒ‹–¼‚Ì•Ï”
    
    newFN = _
        "C:\Documents and Settings\Seebeck\ƒfƒXƒNƒgƒbƒv\Result\" & FileName.Text & ".xls"
                                                'V‹Kì¬ƒtƒ@ƒCƒ‹–¼‚ÌŽæ“¾
    
    ActiveWorkbook.SaveCopyAs FileName:=newFN   'ƒtƒ@ƒCƒ‹‚ðƒRƒs[‚µ‚Ä•Û‘¶
    
End Sub


