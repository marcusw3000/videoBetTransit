var url_imagens = '/Upload/Imagens/';
var url_arquivos = '/Upload/Arquivos/';

/*DIVISAO REGIONAL*/
var FileRegionalXML = '/Upload/XML/Estatico/regionais.xml';
var FileMapaRegionalXML = '/Upload/XML/Estatico/regionalcoords.xml';
var FileMunicipiosXML = '/Upload/XML/Estatico/Municipios_Regionais.xml'
/*CAMERAS*/
var FileCamXML = '/Upload/XML/cameraslivestream.xml';
var url_cameras = '/Upload/Cameras/';
var url_cameras_status = '/Upload/Cameras/Status/';
/*CONDI�?�?ES DE RODOVIA TEMP*/
var FileCamXML2 = '/Upload/XML/cameraslive.xml';
/*INSTITUCIONAL UBAS*/
var FileUBACoordsXML = '/Upload/XML/Estatico/ubascoords.xml';
var FileUBARegionais = '/Upload/XML/UBAs.xml';
/*INSTITUCIONAL DENOMINA�?�?O DE CAMERAS*/
var FileDenPesquisaXML = '/Upload/XML/denominacoesGRID.xml';
var FileDenDetalhesXML = '/Upload/XML/denominacoesDetalhes.xml';
var aXMLDenPesquisa = new Array();
var aXMLDenDetalhes = new Array();
/*CAMPANHA*/
var FileCampanhaXML = '/Upload/XML/campanha.xml';
var aXMLCampanha = new Array();
/*CURSOTREINAMENTO*/
var FileCursoTreinamentoXML = '/Upload/XML/cursotreinamento.xml';
var aXMLCursoTreinamento = new Array();
/*RADAR*/
var FileRadaresXML = '/Upload/XML/radares.xml';
var aXMLRadar = new Array();
/*CONTROLES*/
var FileControlesXML = '/Upload/XML/controles.xml';
var aXMLControles = new Array();
/*PONTO DE PESAGEM*/
var FilePontoPesagemXML = '/Upload/XML/balancas.xml';
/*RESTRICAO DE TRANSITO*/
var FileRestricaoXML = '/Upload/XML/restricao.xml';
var FileVeiculoRestricaoXML = '/Upload/XML/veiculorestricao.xml';
/*EDITAL*/
var FileEditaisXML = '/Upload/XML/editais.xml';
var aXMLEditaisModal = new Array();
var aXMLEditais = new Array();
var aXMLEditaisNro = new Array();
var aXMLEditaisDatas = new Array();


/*Condição das Rodovias*/
var FileCondicaoRodoviasXML = '/Upload/XML/condicaoRodovias.xml';
var aXMLCondicaoRodovias = new Array();

/*Policial Rodoviário*/
var FilePolicialRodoviarioXML = '/Upload/XML/policial_rodoviario.xml';
var aXMLAgentes = new Array();

/*Desapropriaçoes*/
var FileRelDesapropriacoesXML = '/Upload/XML/InformacoesDesapropriacoes.xml';
var aXMLDesapropriacoes = new Array();

/*Desapropriação Situação Quantidade*/
var FileRelDesapropriacaoSituacaoQuantidadeXML = '/Upload/XML/DesapropriacaoSituacaoQuantidade.xml';
var aXMLDesapropriacaoSituacaoQuantidade = new Array();

/*AUDIENCIA PUBLICA*/
var FileAudienciaXML = '/Upload/XML/audiencia.xml';
var aXMLAudiencia = new Array();


/*AUDIENCIA PUBLICA*/
var FileManifestacaoXML = '/Upload/XML/manifestacao.xml';
var aXMLManifestacao = new Array();


/*HOME INDEX*/
var FileBannerXML = '/Upload/XML/banner.xml';
var aXMLBanner = new Array();
/*HOME INDEX*/
var FileNoticiaXML = '/Upload/XML/noticiaHome.xml';
var aXMLNoticia = new Array();
/*RODOVIAS INTERDITADAS*/
var FileRestricaoXML = '/Upload/XML/restricao.xml';
var aXMLRestricao = new Array();

var Functions = {
    htmlEscape: function (str) {
        return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    },
    ClearFormClick: function (controle) {
        $(controle).click(function () {
            Functions.ClearForm();
        });
    },
    ClearForm: function () {
        $("form").find(':input').each(function () {
            switch (this.type) {
                case 'password':
                case 'select-multiple':
                case 'select-one':
                case 'text':
                case 'textarea':
                    $(this).val('');
                    break;
                case 'checkbox':
                case 'radio':
                    this.checked = false;
            }
        });
    },
    somenteLetras: function () {
        if (!(event.keyCode < 48 || event.keyCode > 57)) {
            return true;
        }
        else {
            e.preventDefault();
            return false;
        }
    },
    somenteLetraseNumeros: function (controle) {
        if (!(event.keyCode >= 65 && event.keyCode <= 90) && !(event.keyCode >= 97 && event.keyCode <= 122) && !(event.keyCode >= 48 && event.keyCode <= 57)) {
            if (event.keyCode == 13) {
                controle.focus();
            } else {
                return false;
            }
        }
        return false;
    },
    somenteNumeros: function (e) {
        var tecla = (window.event) ? event.keyCode : e.which;
        if ((tecla > 47 && tecla < 58)) {
            return true;
        } else {
            return false;
        }
    },
    validaData: function (controle) {
        var $valor = $(controle).val();
        if ($valor) {

            var $erro = "";
            var expReg = /^((0[1-9]|[12][0-9]|3[01])\/(0[1-9]|1[012])\/[1-2][0-9]\d{2})$/;

            if ($valor.match(expReg)) {

                var $dia = parseFloat($valor.substring(0, 2));
                var $mes = parseFloat($valor.substring(3, 5));
                var $ano = parseFloat($valor.substring(6, 10));

                if (($mes == 4 && $dia > 30) || ($mes == 6 && $dia > 30) || ($mes == 9 && $dia > 30) || ($mes == 11 && $dia > 30)) {
                    $erro = "Data incorreta! O  mês especificado na data " + $valor + " cont&eacute;m 30 dias.";
                } else {
                    if ($ano % 4 != 0 && $mes == 2 && $dia > 28) {
                        $erro = "Data incorreta! O  mês especificado na data " + $valor + " contém 28 dias.";
                    } else {
                        if ($ano % 4 == 0 && $mes == 2 && $dia > 29) { $erro = "Data incorreta! O mês especificado na data " + $valor + " contém 29 dias."; }
                    }
                }
            } else {
                $erro = "Formato de Data para " + $valor + " &eacute; inv&aacute;lido!";
            }

            if ($erro) {
                $(controle).val('');
                $(document).focusout();
                alert($erro);
            } else {
                return $(this);
            }
        } else {
            return $(this);
        }
    },
    LoadPage: function (url, metodo, data, controleResult) {
        $.ajax({
            url: url,
            type: metodo,
            dataType: "html",
            data: data,
            async: false,
            error: function () { alert("Não foi possivel processar!"); },
            success: function (msg) {
                $(controleResult).html(msg);
            }
        }
     );
    },
    LoadCidade: function (controle) {
        var sel = $(controle);
        $.ajax({
            type: "GET",
            url: '/Upload/XML/municipios.xml',
            dataType: "xml",
            error: function () { alert("Erro de processamento nos Municipios "); },
            success: function (xml) {
                $(controle).append(new Option('', ''));

                $(xml).find('Municipios').each(function () {
                    var temp = new Option($(this).find('Municipio').text(), $(this).find('ID').text());
                    sel[0].options[sel[0].options.length] = temp;
                });

                $(controle).append($(controle + "option").remove().sort(function (a, b) {
                    var at = $(a).text(), bt = $(b).text();
                    return (at > bt) ? 1 : ((at < bt) ? -1 : 0);
                }));

            }
        });
    },
    LoadRodovias: function (controle) {
        var sel = $(controle);
        var x = '';
        $.ajax({
            type: "GET",
            url: '/Upload/XML/Rodovias.xml',
            dataType: "xml",
            error: function () { alert("Erro de processamento nas Rodovias "); },
            success: function (xml) {
                $(controle).append(new Option('Todas', ''));
                $(xml).find('Rodovias').each(function () {
                    if ($(this).find('Rodovia').text() != x) {
                        var temp = new Option($(this).find('Rodovia').text(), $(this).find('Rodovia').text());
                        sel[0].options[sel[0].options.length] = temp;
                        x = $(this).find('Rodovia').text();
                    }
                });

            }
        });
    },
    Validar: function (theCPF) {

        if (theCPF.val() == "") { return (false); }

        if (((theCPF.val().length == 11) && (theCPF.val() == '11111111111') || (theCPF.val() == '22222222222') || (theCPF.val() == '33333333333') || (theCPF.val() == '44444444444') || (theCPF.val() == '55555555555') || (theCPF.val() == '66666666666') || (theCPF.val() == '77777777777') || (theCPF.val() == '88888888888') || (theCPF.val() == '99999999999') || (theCPF.val() == '00000000000')))
        { return (false); }

        //if (!((theCPF.val().length == 11) || (theCPF.val().length == 14))) { return (false); }
        var checkOK = "0123456789";
        var checkStr = theCPF.val().replace('.', '').replace('/', '').replace('-', '').replace(',', '').replace('.', '');
        //alert(checkStr);
        var allValid = true;
        var allNum = "";
        for (i = 0; i < checkStr.length; i++) {
            ch = checkStr.charAt(i);
            for (j = 0; j < checkOK.length; j++)
                if (ch == checkOK.charAt(j)) break;
            if (j == checkOK.length)
            { allValid = false; break; }
            allNum += ch;
        }

        if (!allValid) { return (false); }
        var chkVal = allNum;
        var prsVal = parseFloat(allNum);
        if (chkVal != "" && !(prsVal > "0"))
        { return (false); }

        if (checkStr.length == 11) {
            var tot = 0;
            for (i = 2; i <= 10; i++) { tot += i * parseInt(checkStr.charAt(10 - i)); }
            if ((tot * 10 % 11 % 10) != parseInt(checkStr.charAt(9))) { return (false); }
            tot = 0;
            for (i = 2; i <= 11; i++) { tot += i * parseInt(checkStr.charAt(11 - i)); }
            if ((tot * 10 % 11 % 10) != parseInt(checkStr.charAt(10))) { return (false); }
        }
        else {
            var tot = 0;
            var peso = 2;
            for (i = 0; i <= 11; i++) {
                tot += peso * parseInt(checkStr.charAt(11 - i));
                peso++;
                if (peso == 10) { peso = 2; }
            }

            if ((tot * 10 % 11 % 10) != parseInt(checkStr.charAt(12))) { return (false); }

            tot = 0;
            peso = 2;
            for (i = 0; i <= 12; i++) {
                tot += peso * parseInt(checkStr.charAt(12 - i));
                peso++;
                if (peso == 10) { peso = 2; }
            }

            if ((tot * 10 % 11 % 10) != parseInt(checkStr.charAt(13)))
            { return (false); }
        }
        return (true);
    }, ResetarSetas: function () {
        $("#ulMenu li").each(function () {
            $(this).removeClass("SetaDesabilitada");
            $(this).removeClass("SetaHabilitada");
            $(this).addClass("SetaDesabilitada");
        });
    },
    HabilitarSeta: function () {
        $("#ulMenu li").click(function () {
            $(this).removeClass('SetaDesabilitada');
            $(this).removeClass('SetaHabilitada');
            $(this).addClass('SetaHabilitada');
        });
    },
    LimparControles: function (controle) {
        $('#' + controle).hide("fast");
        $("#ulMenu li").click(function () {
            var id = $(this).attr('data-value');
            $("#ulMenu li").each(function () {
                var idEach = $(this).attr('data-value');
                if (id != idEach) {
                    $('#' + idEach).hide("fast");
                }
            });
        });
    },
    ControlePage: function (id) {
        $('#' + id).show("fast");
        $('body,html').animate({ scrollTop: 0 }, 0);
    }
};
