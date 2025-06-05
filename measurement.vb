'------------------------------------------------------------------
' Seebeck Measurement Program
'       by KEITHLEY 2182A & KEITHLEY 2700 (ver.1.0, 2016/07/26)
'------------------------------------------------------------------

'                       2016/10/18: ver.1.0: 'ª'èƒvƒƒOƒ‰ƒ€ƒŠƒŠ[ƒX by Y.SUZUKI
'
    Dim bCancel As Boolean  'ƒNƒCƒbƒgƒ{ƒ^ƒ"‚ÌŽÀs—L–³
#If VBA7 Then
    Private Declare PtrSafe Function GetTickCount Lib "kernel32" () As Long
    Private Declare PtrSafe Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As Long)
#Else
    Private Declare Function GetTickCount Lib "kernel32" () As Long
    Private Declare Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As Long)
#End If

' VISA COM declarations
Dim rm As Object
Dim session2182A As Object
Dim session2700 As Object
Dim sessionPK160 As Object

' Helper to open VISA sessions
Sub OpenVisaSessions()
    Set rm = CreateObject("VISA.GlobalResourceManager")
    Set session2182A = rm.Open("GPIB0::7::INSTR")    ' Keithley 2182A
    Set session2700 = rm.Open("GPIB0::16::INSTR")    ' Keithley 2700
    Set sessionPK160 = rm.Open("GPIB0::15::INSTR")   ' PK160 (if needed)
End Sub

' Helper to close VISA sessions
Sub CloseVisaSessions()
    On Error Resume Next
    session2182A.Close
    session2700.Close
    sessionPK160.Close
    Set session2182A = Nothing
    Set session2700 = Nothing
    Set sessionPK160 = Nothing
    Set rm = Nothing
End Sub

' Helper to send a command
Sub VisaSend(session As Object, cmd As String)
    session.WriteString cmd
End Sub

' Helper to query a value
Function VisaQuery(session As Object, cmd As String) As String
    session.WriteString cmd
    VisaQuery = session.ReadString
End Function

' Main measurement logic
Sub RunMeasurement()
    Dim j As Integer, kaisuu1 As Integer, kaisuu2 As Integer, kaisuu3 As Integer, kaisuu4 As Integer, kaisuu As Integer
    Dim tcTime As Double
    Dim v0 As Double, v1 As Double, incRate As Double, decRate As Double
    Dim preTime As Integer, periodTime As Integer, holdTime As Integer
    Dim volt As Double, temf As Double, temp1 As Double, temp2 As Double
    Dim bCancel As Boolean
    Dim r As String

    v0 = StartVolt.Value
    v1 = StopVolt.Value
    incRate = HeatingRate.Value / 1000
    decRate = CoolingRate.Value / 1000
    periodTime = Period.Value
    holdTime = Hold.Value
    preTime = Pre.Value

    Application.StatusBar = "Initializing"
    QuitButton.SetFocus
    bCancel = False

    Cells.Clear
    With Range("A1"): .ColumnWidth = 8: .Value = "Time [s]": End With
    With Range("B1"): .ColumnWidth = 12: .Value = "TEMF [mV]": End With
    With Range("C1"): .ColumnWidth = 12: .Value = "Temp1[oC]": End With
    With Range("D1"): .Value = "Temp2[oC]": End With

    ' Open VISA sessions
    OpenVisaSessions

    ' Instrument initialization
    VisaSend session2182A, "*RST"
    VisaSend session2700, "*RST"
    VisaSend sessionPK160, "#1 REN"
    VisaSend sessionPK160, "#1 VCN 100"
    VisaSend sessionPK160, "#1 OCP 100"
    VisaSend sessionPK160, "#1 SW1"

    ' Keithley 2182A config
    VisaSend session2182A, ":CONF:volt"
    VisaSend session2182A, ":VOLT:DIGITS 8"
    VisaSend session2182A, ":VOLT:NPLC 5"

    ' Keithley 2700 config
    VisaSend session2700, ":CONF:TEMP"
    VisaSend session2700, ":UNIT:TEMP C"
    VisaSend session2700, ":TEMP:TRAN TC"
    VisaSend session2700, ":TEMP:TC:TYPE K"
    VisaSend session2700, ":TEMP:TC:RJUN:RSEL EXT"
    VisaSend session2700, ":TEMP:NPLC 5"

    ' Calculate loop counts
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

    volt = v0
    VisaSend sessionPK160, "#1 ISET" & volt
    j = 2
    kaisuu = 1
    Application.Wait (Now + TimeValue("0:00:02"))

    Do While bCancel = False
        tcTime = Timer
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
        VisaSend sessionPK160, "#1 ISET" & volt
        Cells(j, 1).Value = (j - 2) * periodTime
        ' Measure voltage on Channel 1 for KEITHLEY 2182A
        temf = Val(VisaQuery(session2182A, ":READ?")) * 1000
        Cells(j, 2).Value = temf
        ' Measure temperature for KEITHLEY 2700
        VisaSend session2700, ":ROUT:CLOS (@102)"
        temp1 = Val(VisaQuery(session2700, ":READ?"))
        Cells(j, 3).Value = temp1
        VisaSend session2700, ":ROUT:CLOS (@104)"
        temp2 = Val(VisaQuery(session2700, ":READ?"))
        Cells(j, 4).Value = temp2
        Application.StatusBar = "Measuring :" & (j - 2) * periodTime & "[s], " & temf & "[mV], " & temp1 & "[C], " & temp2 & "[C]"
        j = j + 1
        kaisuu = kaisuu + 1
        Dim elapsed As Double
        elapsed = (Timer - tcTime)
        If elapsed < periodTime Then
            Application.Wait (Now + TimeValue("0:00:" & Format(periodTime - elapsed, "00")))
        End If
        DoEvents
    Loop
    VisaSend sessionPK160, "#1 SW0"
    Application.StatusBar = "Done"
    SaveButton.SetFocus
    CloseVisaSessions
End Sub

' Add a public macro to launch the measurement dialog
Sub StartMeasurement()
    Measurement.Show
End Sub

Private Sub CommandButton1_Click()
    RunMeasurement
End Sub

Private Sub CoolingRate_Change()

End Sub

Private Sub QuitButton_Click()
    bCancel = True      'ƒNƒCƒbƒgƒ{ƒ^ƒ"‚Ìˆ—
End Sub

Private Sub SaveButton_Click()
    Dim newFN As String                         'V‹Kì¬ƒtƒ@ƒCƒ‹–¼‚Ì•Ï"
    
    newFN = _
        "C:\Documents and Settings\Seebeck\ƒfƒXƒNƒgƒbƒv\Result\" & FileName.Text & ".xls"
                                                'V‹Kì¬ƒtƒ@ƒCƒ‹–¼‚ÌŽæ"¾
    
    ActiveWorkbook.SaveCopyAs FileName:=newFN   'ƒtƒ@ƒCƒ‹‚ðƒRƒs[‚µ‚Ä•Û'¶
End Sub


