object MainForm: TMainForm
  Left = 100
  Top = 100
  Width = 640
  Height = 480
  Caption = 'Sample Form'
  OnCreate = FormCreate
  OnDestroy = FormDestroy
  object Panel1: TPanel
    Align = alTop
    Height = 40
    object ButtonOK: TButton
      Caption = 'OK'
      OnClick = ButtonOKClick
    end
    object ButtonCancel: TButton
      Caption = 'Cancel'
      OnClick = ButtonCancelClick
    end
  end
  object Memo1: TMemo
    Align = alClient
    OnChange = Memo1Change
  end
  object StatusBar1: TStatusBar
    Align = alBottom
  end
end
