namespace TrafficCounter.Api.Models;

// ── Live Detection Frame (recebido do Python) ──

public class LiveDetectionFrameDto
{
    public string CameraId { get; set; } = string.Empty;
    public string RoundId { get; set; } = string.Empty;
    public int FrameWidth { get; set; }
    public int FrameHeight { get; set; }
    public int TotalCount { get; set; }
    public double Timestamp { get; set; }
    public RoiDto Roi { get; set; } = new();
    public CountLineDto CountLine { get; set; } = new();
    public List<DetectionDto> Detections { get; set; } = new();
}

public class DetectionDto
{
    public string TrackId { get; set; } = string.Empty;
    public string VehicleType { get; set; } = string.Empty;
    public BoundingBoxDto Bbox { get; set; } = new();
    public PointDto Center { get; set; } = new();
    public double Confidence { get; set; }
    public bool InsideRoi { get; set; }
    public bool CrossedLine { get; set; }
    public bool Counted { get; set; }
    public string? SnapshotUrl { get; set; }
}

public class BoundingBoxDto
{
    public int X { get; set; }
    public int Y { get; set; }
    public int W { get; set; }
    public int H { get; set; }
}

public class PointDto
{
    public int X { get; set; }
    public int Y { get; set; }
}

public class RoiDto
{
    public int X { get; set; }
    public int Y { get; set; }
    public int W { get; set; }
    public int H { get; set; }
}

public class CountLineDto
{
    public int X1 { get; set; }
    public int Y1 { get; set; }
    public int X2 { get; set; }
    public int Y2 { get; set; }
}

// ── Camera Config ──

public class CameraConfigDto
{
    public string CameraId { get; set; } = string.Empty;
    public RoiDto Roi { get; set; } = new();
    public CountLineDto CountLine { get; set; } = new();
    public string CountDirection { get; set; } = "any";
}

public class CameraConfig
{
    public string CameraId { get; set; } = string.Empty;
    public int RoiX { get; set; }
    public int RoiY { get; set; }
    public int RoiW { get; set; }
    public int RoiH { get; set; }
    public int CountLineX1 { get; set; }
    public int CountLineY1 { get; set; }
    public int CountLineX2 { get; set; }
    public int CountLineY2 { get; set; }
    public string CountDirection { get; set; } = "any";
}
