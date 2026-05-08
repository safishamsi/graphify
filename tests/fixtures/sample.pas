unit SampleUnit;

interface

uses
  SysUtils, Classes;

type
  IProcessor = interface
    procedure Process;
    function GetCount: Integer;
  end;

  TBaseProcessor = class(TObject)
  public
    procedure Initialize; virtual;
    function GetCount: Integer; virtual;
  end;

  TDataProcessor = class(TBaseProcessor, IProcessor)
  private
    FCount: Integer;
  public
    constructor Create;
    procedure Initialize; override;
    procedure Process;
    function GetCount: Integer; override;
    procedure Reset;
  end;

implementation

procedure TBaseProcessor.Initialize;
begin
  { base init }
end;

function TBaseProcessor.GetCount: Integer;
begin
  Result := 0;
end;

constructor TDataProcessor.Create;
begin
  inherited;
  FCount := 0;
end;

procedure TDataProcessor.Initialize;
begin
  inherited Initialize;
  FCount := 0;
end;

procedure TDataProcessor.Process;
begin
  Inc(FCount);
  Reset;
end;

function TDataProcessor.GetCount: Integer;
begin
  Result := FCount;
end;

procedure TDataProcessor.Reset;
begin
  FCount := 0;
end;

end.
